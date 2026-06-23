# -*- coding: utf-8 -*-

# External imports
import os
import sys
import cv2
import base64
import tempfile
import subprocess
import uuid
from datetime import timedelta


from flask import Flask, jsonify, send_from_directory, request, send_file
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity, decode_token
from flask_socketio import SocketIO, join_room
import json
import traceback


segment_anything_path = os.path.join(os.path.dirname(__file__), 'segment-anything-2')
if segment_anything_path not in sys.path:
    sys.path.append(segment_anything_path)

# Local imports
from video_processor import VideoProcessor
from video_effects_processor import VideoEffectsProcessor
from video_animation_processor import VideoAnimationProcessor
from video_compositor import *
from sam2.build_sam import build_sam2
from sam2_segmenter import SAM2Segmenter
from data_saver import DataSaver
from utils import *
from text_generator import create_text_frame
import storage
import ws_listener
from celery.result import AsyncResult
from tasks import celery_app, generate_video_masks, publish_job_progress
from auth import db, auth_bp

app = Flask(__name__)

app.debug = True  # Ativa o modo debug
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.environ['JWT_SECRET_KEY']
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=12)  # sessão de edição pode durar bastante tempo

db.init_app(app)
JWTManager(app)
app.register_blueprint(auth_bp, url_prefix='/auth')

with app.app_context():
    db.create_all()

# async_mode='threading' de propósito: eventlet/gevent fazem monkey-patch do stdlib
# (socket, threading, etc.) o que entra em conflito com torch/CUDA usados no mesmo processo
# pelo SAM2Segmenter em /video/frame/mask.
# Sem message_queue: o ws_listener.py já distribui o progresso entre pods via Redis
# pub/sub manualmente (cada pod só emite para clientes ligados a ele), por isso o
# adapter Redis nativo do SocketIO seria redundante (e duplicaria as mensagens).
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
)


@socketio.on('connect')
def on_socket_connect(auth):
    token = (auth or {}).get('token')
    if not token:
        return False

    try:
        decode_token(token)
    except Exception:
        return False


@socketio.on('subscribe_job')
def on_subscribe_job(data):
    job_id = (data or {}).get('job_id')
    if job_id:
        join_room(f'job_{job_id}')


ws_listener.start_listener(socketio)

# Definição da pasta de imagens
IMAGES_FOLDER = 'images'
SEGMENTED_FOLDER = 'segmented'
# DEFINIR PASTA DE PROJETOS
PROJECTS_FOLDER = 'projects'

# Criar pastas se não existirem
os.makedirs(IMAGES_FOLDER, exist_ok=True)
os.makedirs(SEGMENTED_FOLDER, exist_ok=True)
os.makedirs(PROJECTS_FOLDER, exist_ok=True)

@app.route('/test')
def test():
    """Rota de teste para verificar se a API está funcionando"""
    return jsonify({'message': 'API funcionando'})

@app.route('/images')
def get_images():
    """Lista todas as imagens disponíveis na pasta"""
    try:
        images = [f for f in os.listdir(IMAGES_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        return jsonify({'images': images})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/images/<image_name>')
def get_image(image_name):
    """Serve um arquivo de imagem"""
    try:
        return send_from_directory(IMAGES_FOLDER, image_name)
    except Exception as e:
        return jsonify({'error': f'Erro ao buscar a imagem: {str(e)}'}), 500

@app.route('/segmentar/<image_name>', methods=['POST'])
def segmentar_image(image_name):
    """Executa a segmentação na imagem e retorna a versão segmentada"""
    input_path = os.path.join(IMAGES_FOLDER, image_name)
    output_path = os.path.join(SEGMENTED_FOLDER, f'seg_{image_name}')

    if not os.path.exists(input_path):
        return jsonify({'error': 'Imagem não encontrada'}), 404

    try:
        # Executa o script SAM2 para segmentação
        subprocess.run(['python', 'run_sam2.py', input_path, output_path])
        return jsonify({'segmented_image': f'seg_{image_name}'})
    except Exception as e:
        return jsonify({'error': f'Erro ao segmentar imagem: {str(e)}'}), 500
    
    
# ONLY ROUTES BELOW ARE USED
@app.route('/convert/image-to-video', methods=['POST'])
@jwt_required()
def convert_image_to_video():
    image_file = request.files.get('image')
    if not image_file:
        return jsonify({'error': 'No image file provided'}), 400

    # Ler a imagem como frame
    file_bytes = np.frombuffer(image_file.read(), np.uint8)
    frame = cv2.imdecode(file_bytes, cv2.IMREAD_UNCHANGED)

    if frame is None:
        return jsonify({'error': 'Invalid image file'}), 400

    # Criar ficheiros temporários
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_in, \
         tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_out:
        temp_input = tmp_in.name
        temp_output = tmp_out.name

    try:
        # Criar vídeo simples com a imagem
        convert_frame_to_video(frame, duration=5.0, output_path=temp_input, fps=30)

        # Comprimir e preparar com comp_browser
        comp_browser(
            input_path=temp_input,
            output_path=temp_output,
            crf=23,
            preset='fast',
            audio_codec='aac',
            video_codec='libx264'
        )

        # Enviar vídeo final como resposta
        return send_file(temp_output, mimetype='video/mp4', as_attachment=True, download_name='converted.mp4')

    finally:
        for path in [temp_input, temp_output]:
            if os.path.exists(path):
                os.remove(path)
    
@app.route('/video/basic_data', methods=['POST'])
@jwt_required()
def get_basic_video_data():
    file = request.files['video']

    # Arquivo temporário com sufixo mp4 para o OpenCV abrir
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
        file.save(tmp.name)
        temp_path = tmp.name

    processor = None

    try:
        processor = VideoProcessor(temp_path)
        num_frames = processor.get_num_frames()
        fps = processor.get_fps()

        frames_indices = get_interpolated_numbers(0, num_frames - 1, 10)
        frames = []

        for i in frames_indices:
            frame = processor.get_frame(i)
            if frame is None:
                continue
            frame = resize_frame(frame, width=100)
            _, buffer = cv2.imencode('.jpg', frame)
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            frames.append(f"data:image/jpeg;base64,{frame_base64}")

        print('Fps: ', fps)
        print('Frames: ', len(frames))
        return jsonify({'fps': fps, 'frames': frames})

    finally:
        if processor:
            processor.release()
        try:
            os.remove(temp_path)
        except PermissionError:
            print(f"Não foi possível remover o arquivo: {temp_path}")

@app.route('/video/frame/mask', methods=['POST'])
@jwt_required()
def get_masks_of_frame():
    file = request.files['frame']

    # Guardar imagem temporária
    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
        file.save(tmp.name)
        temp_path = tmp.name

    try:
        segmenter = SAM2Segmenter()
        image_bgr, image_rgb, sam_result = segmenter.generate_mask_for_image(temp_path)
        #segmenter.show_sam_result(image_bgr, sam_result)

        # Codificar imagem original para base64
        _, buffer = cv2.imencode('.jpg', image_bgr)
        image_base64 = base64.b64encode(buffer).decode('utf-8')

        # Extrair apenas as masks
        masks = []
        for idx, mask_data in enumerate(sam_result):
            mask = mask_data['segmentation'].astype(np.uint8) * 255
            _, buffer = cv2.imencode('.png', mask)
            mask_base64 = base64.b64encode(buffer).decode('utf-8')
            masks.append({
                'id': idx,
                'mask': f"data:image/png;base64,{mask_base64}"
            })

        return jsonify({
            'image': f"data:image/jpeg;base64,{image_base64}",
            'masks': masks
        })
    finally:
        try:
            os.remove(temp_path)
        except PermissionError:
            print(f"Não foi possível remover o arquivo: {temp_path}")

@app.route('/video/mask', methods=['POST'])
@jwt_required()
def get_masks_of_video():
    # Verificar se o vídeo foi enviado
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400

    file = request.files['video']

    try:
        # Extrair parâmetros do form
        stage_name = request.form.get('stage_name')
        start_frame = int(request.form.get('start_frame', 0))
        end_frame = int(request.form.get('end_frame', -1))  # -1 significa até o final
        scale_factor = float(request.form.get('scale_factor', 0.5))

        video_objects_json = request.form.get('video_objects')
        video_objects_raw = json.loads(video_objects_json)

        # Validar os pontos e labels antes de despachar a task
        for idx, obj in enumerate(video_objects_raw):
            points_raw = obj.get('points')
            labels_raw = obj.get('labels')

            if not points_raw or not labels_raw:
                return jsonify({'error': f'Points and labels cannot be empty (object index {idx})'}), 400

            if len(points_raw) != len(labels_raw):
                return jsonify({'error': f'Points and labels must have the same length (object index {idx})'}), 400

        print(f'Stage name: {stage_name}')
        print(f"Fator de escala: {scale_factor}")
        print(f"Frame inicial: {start_frame}")
        print(f"Frame final: {end_frame}")

        # Se já existirem máscaras geradas para este stage, devolver de imediato
        cached_result = DataSaver.get_stage(stage_name) if stage_name else None
        if cached_result:
            print('Máscaras já existentes para o stage:', stage_name)
            return jsonify({'status': 'done', 'result': cached_result, 'track_id': stage_name})

        # Guardar o vídeo no MinIO/R2 para o worker conseguir descarregá-lo
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
            file.save(tmp.name)
            temp_path = tmp.name

        video_key = f"uploads/{uuid.uuid4().hex}.mp4"
        try:
            storage.upload_file(temp_path, storage.VIDEOS_BUCKET, video_key)
        finally:
            os.remove(temp_path)

        # Despachar a task Celery e devolver o job_id imediatamente
        task = generate_video_masks.delay(
            video_key=video_key,
            video_objects_json=video_objects_json,
            scale_factor=scale_factor,
            start_frame=start_frame,
            end_frame=end_frame,
            stage_name=stage_name,
        )

        return jsonify({'status': 'pending', 'job_id': task.id}), 202

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/video/mask/status/<job_id>', methods=['GET'])
@jwt_required()
def get_video_mask_status(job_id):
    task = AsyncResult(job_id, app=celery_app)

    if task.state == 'PROGRESS':
        stage = task.info.get('stage') if isinstance(task.info, dict) else None
        return jsonify({'status': 'pending', 'stage': stage})

    if task.state in ('PENDING', 'STARTED', 'RETRY'):
        return jsonify({'status': 'pending'})

    if task.state == 'FAILURE':
        return jsonify({'status': 'failed', 'error': str(task.result)})

    if task.state == 'SUCCESS':
        payload = task.result
        result = DataSaver.get_stage(payload['track_id'])
        return jsonify({'status': 'done', 'result': result, 'track_id': payload['track_id']})

    if task.state == 'REVOKED':
        return jsonify({'status': 'cancelled'})

    return jsonify({'status': task.state.lower()})


@app.route('/video/mask/<job_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_video_mask_job(job_id):
    # terminate=True: o worker está a correr a inferência SAM2 de forma síncrona
    # (sem checkpoints de cancelamento), por isso só matar o processo do worker
    # interrompe a task de facto. Pode deixar ficheiros temporários por limpar.
    celery_app.control.revoke(job_id, terminate=True)
    publish_job_progress(job_id, {'status': 'cancelled'})
    return jsonify({'status': 'cancelled'}), 200

@app.route('/projects', methods=['POST'])
@jwt_required()
def save_project():
    print("\nRota para salvar um projeto\n")
    try:
        project = request.get_json()

        name = project.get('name')
        email = get_jwt_identity()
        data = project.get('data')
        thumbnail = project.get('thumbnail', None)

        if not name or not email or not data:
            return jsonify({'error': 'Nome, email e dados do projeto são obrigatórios'}), 400
        
        user_folder = os.path.join(PROJECTS_FOLDER, email)
        os.makedirs(user_folder, exist_ok=True)

        # gerar ID unico para o projeto
        projectId = str(int(time.time() * 1000))  # ID baseado no timestamp atual

        # guardar como ficheiro JSON
        project_path = os.path.join(user_folder, f'{projectId}.json')
        with open(project_path, 'w') as f:
            json.dump({
                'name': name,
                'email': email,
                'data': data,
                'thumbnail': thumbnail,
                'projectId': projectId
            }, f, indent=2) # o q faz com o indent=2 é que formata o JSON para ficar mais legível
        return jsonify({
            'id': projectId,
            'name': name,
            'user_email': email,
            'thumbnail': thumbnail,
        }), 201
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
@jwt_required()
def download():
    print("\n=== INÍCIO DA REQUISIÇÃO DE DOWNLOAD ===")

    try:
        user_id = get_jwt_identity()

        # Log de cabeçalhos da requisição
        print("\n[HEADERS]")
        for key, value in request.headers.items():
            print(f"{key}: {value}")

        # Verificar se há vídeos
        if 'videos[]' not in request.files:
            print("\n[ERRO] Nenhum vídeo encontrado nos arquivos enviados")
            return jsonify({'error': 'Nenhum vídeo enviado'}), 400

        # Obter todos os vídeos
        videos = request.files.getlist('videos[]')
        print(f"\n[VIDEOS ENVIADOS] {len(videos)} vídeo(s) recebido(s)")
        
        for idx, video in enumerate(videos):
            print(f"\nVideo {idx + 1}:")
            print(f"Nome: {video.filename}")
            print(f"Tipo: {video.content_type}")
            print(f"Tamanho: {len(video.read())} bytes")
            video.seek(0)  # Volta ao início do arquivo após ler

        # Obter metadados (se existirem)
        metadata = {}
        if 'metadata' in request.form:
            metadata = json.loads(request.form['metadata'])
            print("\n[METADADOS RECEBIDOS]")
            print(json.dumps(metadata, indent=2))
        else:
            print("\n[AVISO] Nenhum metadado recebido")

        fps = metadata.get('fps', None)
        width = metadata.get('width', None)
        height = metadata.get('height', None)
        enable_transparency = metadata.get('enable_transparency', True)
        if not width or not height:
            print("\n[AVISO] Nenhuma largura ou altura especificada nos metadados")
            return jsonify({'error': 'Largura ou altura não especificada nos metadados'}), 400

        # Cria pasta de projetos para o user_id
        user_folder = os.path.join('projects', str(user_id))
        os.makedirs(user_folder, exist_ok=True)

        # Criar diretório temporário
        temp_dir = tempfile.mkdtemp()
        compositor = VideoCompositor(
            output_path=os.path.join(temp_dir, f'output.mp4'),
            output_width=width,  # Ajuste conforme necessário
            output_height=height,
            fps=fps
        )
        effectProcessor = VideoEffectsProcessor()
        animationProcessor = VideoAnimationProcessor()

        elements_metadata = metadata.get('elements_data', {})
        video_data = {}
        count_video = 0
        for idx, video_id in enumerate(elements_metadata.keys()):
            element_metadata = elements_metadata.get(video_id, {})
            if not element_metadata:
                print(f"\n[AVISO] Nenhum metadado encontrado para o vídeo {video_id}")
                print('\tVideos data:', elements_metadata)
                print('\tVideo metadata:', element_metadata)
                continue
            element_type = element_metadata.get('type', 'video')
            rotation = element_metadata.get('rotation', 0)
            flipped = element_metadata.get('flipped', False)
            opacity = element_metadata.get('opacity', 1.0)
            border_radius = element_metadata.get('borderRadius', 0)
            speed = element_metadata.get('speed', 1)
            draw = element_metadata.get('draw', True)
            st_offset = element_metadata.get('st_offset', 0)
            start_t = element_metadata.get('start_t', 0)
            end_t = element_metadata.get('end_t', None)
            effects = element_metadata.get('effects', {})
            animations = element_metadata.get('animations', [])
            rect = Rect(
                int(element_metadata.get('x', 0)),
                int(element_metadata.get('y', 0)),
                int(element_metadata.get('width', None)),
                int(element_metadata.get('height', None))
            )
            
            if element_type == 'video':
                chromaKeyData = element_metadata.get('chromaKeyDetectionData', {})
                stageMasks = element_metadata.get('stageMasks', None)
                masks = decode_masks(DataSaver.get_stage(stageMasks) or {}) if stageMasks else None    
                video_file = videos[count_video]   
                count_video += 1                 
                video_data[idx] = {
                    'idx': idx,
                    'video_id': video_id,
                    'video_file': video_file,
                    'effects': effects,
                    'animations': animations,
                    'stageMasks': stageMasks,
                    'masks': masks,
                    'chromaKeyData': chromaKeyData,
                    'rect': rect,
                    'extra_data': {},
                    'rotation': rotation,
                    'flipped': flipped,
                    'draw': draw,
                }
                video_input = os.path.join(temp_dir, f'input_{video_id}.mp4')
                video_file.save(video_input)
                
            elif element_type == 'text':
                text = element_metadata.get('text', '')
                style = element_metadata.get('style', {})
                font_family = style.get('fontFamily', 'Raleway')
                font_size = style.get('fontSize', 20)
                color = style.get('color', '#FFFFFF')
                bold = style.get('fontWeight', 'normal')
                italic = style.get('fontStyle', '')
                align = style.get('textAlign', 'left')
                
                video_data[idx] = {
                    'idx': idx,
                    'video_id': video_id,
                    'effects': effects,
                    'animations': animations,
                    'rect': rect,
                    'extra_data': {},
                    'rotation': rotation,
                    'flipped': flipped,
                    'draw': draw,
                }
                
                # Set the duration of the video clip based on start and end times, or default to 5 seconds if either is missing
                duration = end_t - start_t if start_t and end_t else 5
                
                # Use the given fps, or default to 1 frame per second if not specified
                text_fps = fps or 1
                
                # Determine if the text should be bold — either by numeric weight (>=700) or by string comparison
                is_bold = bold == int(bold) >= 700 if isinstance(bold, int) else bold == 'bold'
                
                # Check if the text style includes italic formatting
                is_italic = 'italic' in italic
                
                # Create a single text frame (image) with the given parameters (font, size, color, etc.)
                text_frame = create_text_frame(text, font_family, font_size, color, is_bold, is_italic,
                                               align, rect.width, rect.height)
                
                # Replicate the static frame into a video array to simulate a video at the specified FPS
                text_frames = replicate_frame_as_video_array(text_frame, duration, text_fps)
                
                # Create a VideoArray object using the generated frames and FPS
                video_input = VideoArray(text_frames, text_fps)
              
            # Add layer with settings
            compositor.add_layer(LayerInfo(
                video=video_input, # Video file or VideoArray
                rect=rect, # Rect object with x, y, width, height
                layer_idx=idx, # Layer index
                st_offset=st_offset, # Start time offset in seconds
                start_t=start_t, # Start time in seconds
                end_t=end_t, # End time in seconds (None means until the end of the video)
                rotation=rotation, # Rotation in degrees
                speed=speed, # Speed multiplier
                flipped=flipped, # Whether the video is flipped horizontally
                draw=draw, # Whether to draw the video
                opacity=opacity, # Opacity of the video layer (0.0 to 1.0)
                border_radius=border_radius, # Border radius for rounded corners
            ))
        
        def process_frame(
            render_info: RenderInfo, 
            frame: np.ndarray, 
            frame_idx: int, 
            fps: int, 
            layer_width: int, 
            layer_height: int, 
            roi_info: RoiInfo,
            render_infos: List[RenderInfo],
            video_time: float,
            global_time: float,
            processing_stage: int,
        ) -> np.ndarray:
            """Função de callback para processar cada frame"""
            video_idx = render_info.layer.layer_idx
            if video_idx not in video_data:
                return frame
            
            rect = video_data[video_idx].get('rect', None)
            masks = video_data[video_idx].get('masks', None)
            effects_config = video_data[video_idx].get('effects', {})
            chromaKeyData = video_data[video_idx].get('chromaKeyData', {})
            extra_data = video_data[video_idx].get('extra_data', None)
            rotation = video_data[video_idx].get('rotation', 0)
            flipped = video_data[video_idx].get('flipped', False)
            animations = video_data[video_idx].get('animations', [])
                        
            if processing_stage == PROCESS_STAGE_POST_TRANSFORM:
                return effectProcessor.process_post_transform(
                    render_info, frame, masks, effects_config, 
                    chromaKeyData, enable_transparency, frame_idx,
                    layer_width, layer_height, roi_info,
                    rect, video_data, extra_data, rotation, flipped, render_infos, video_time
                )
            else:
                frame = animationProcessor.process_animations(frame, animations, global_time, render_info)
                
                return effectProcessor.process_pre_transform(
                    render_info, frame, masks, effects_config, 
                    chromaKeyData, enable_transparency, frame_idx,
                    layer_width, layer_height,
                    rect, video_data, extra_data, flipped, render_infos, video_time
                )
                
        compositor.render(on_frame=process_frame)


        # Retorna o primeiro vídeo processado
        print("\n[RESPOSTA] Enviando vídeo processado:", compositor.output_path)
            
        fd, path = tempfile.mkstemp(suffix='.mp4')
        os.close(fd)  # Fecha o file descriptor

        temp_path = Path(path)

        comp_browser(
            input_path=compositor.output_path,
            output_path=temp_path,
            crf=23,
            preset='fast',
            audio_codec='aac',
            video_codec='libx264'
        )

        return send_file(
            temp_path,
            as_attachment=True,
            download_name='video_processado.mp4'
        )

    except Exception as e:
        traceback.print_exc("\n[ERRO CRÍTICO]", str(e))
        return jsonify({'error': str(e)}), 500

    finally:
        # Limpeza dos arquivos temporários
        try:
            os.remove(compositor.output_path)
            os.remove(temp_path)
        except Exception as e:
            print("Erro na limpeza:", str(e))
        
        print("\n=== FIM DA REQUISIÇÃO ===")

if __name__ == '__main__':
    # use_reloader=False: evita que o reloader do Werkzeug (modo debug) arranque
    # o processo (e a thread do ws_listener) duas vezes
    # allow_unsafe_werkzeug=True: sem eventlet/gevent (de propósito, ver comentário
    # acima do SocketIO), o Flask-SocketIO recusa-se a correr o dev server do Werkzeug
    # sem esta flag. Está aceitável aqui — escala pequena, processo único por pod.
    socketio.run(app, host='0.0.0.0', port=8000, debug=app.debug, use_reloader=False,
                 allow_unsafe_werkzeug=True)
