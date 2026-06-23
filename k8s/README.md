Kubernetes manifests for SAM2 Video VFX Editor

**Architecture**:
- `backend`: Flask REST API for project management, job spawning (JWT auth)
- `worker`: Celery worker for lightweight async tasks (status updates, post-processing)
- `sam2-job`: On-demand Kubernetes Job for SAM2 inference (runs on GPU, spawned by backend)
- `redis`: Celery broker + result backend + WebSocket/SSE state pub/sub
- `postgres`: User accounts, projects, job history
- `minio`: S3-compatible storage for videos, frames, masks, outputs
- `cloudflared`: Cloudflare Tunnel for external HTTPS access
- `CronJob`: Periodic cleanup of old temp files from MinIO

**Deployment Steps**:

1. **Create secrets**:
   ```bash
   cp secrets.env.example secrets.env
   # Edit secrets.env with your values
   kubectl create namespace sam2
   kubectl create secret generic sam2-secrets --from-env-file=secrets.env -n sam2
   ```

2. **Create PVCs** (persistent storage):
   ```bash
   kubectl apply -f pvcs.yaml -n sam2
   ```

3. **Deploy core services**:
   ```bash
   kubectl apply -f namespace.yaml
   kubectl apply -f rbac.yaml -n sam2
   kubectl apply -f postgres.yaml -n sam2
   kubectl apply -f redis.yaml -n sam2
   kubectl apply -f minio.yaml -n sam2
   kubectl apply -f minio_init_job.yaml -n sam2
   ```

4. **Deploy application**:
   ```bash
   kubectl apply -f backend.yaml -n sam2
   kubectl apply -f worker.yaml -n sam2
   kubectl apply -f frontend.yaml -n sam2
   ```

5. **Setup ingress/networking**:
   ```bash
   kubectl apply -f ingress.yaml -n sam2
   kubectl apply -f cloudflared.yaml -n sam2
   kubectl apply -f backup_cronjob.yaml -n sam2
   ```

6. **Autoscaling** (requires `metrics-server` in the cluster):
   ```bash
   kubectl apply -f hpa.yaml -n sam2
   ```

**Build and Push Images**:

Replace image placeholders in manifests with:
- `ghcr.io/your-org/sam2-backend:latest` — Flask API + Celery + Job spawner
- `ghcr.io/your-org/sam2-worker:latest` — Same image as backend, but command: `celery -A tasks worker --loglevel=info`
- `ghcr.io/your-org/sam2-frontend:latest` — Vue.js + Nginx
- `ghcr.io/your-org/sam2-job:latest` — PyTorch + SAM2 model + inference script

See GitHub Actions workflow (`.github/workflows/ci.yml`) for building and pushing images.

**SAM2 Job Spawning**:

Backend creates Jobs by submitting a Kubernetes resource from the `sam2-job-template.yaml` template.
Example API call from backend to spawn a job:
```python
from kubernetes import client, config

config.load_incluster_config()
api = client.BatchV1Api()
job_manifest = {
    "apiVersion": "batch/v1",
    "kind": "Job",
    "metadata": {"name": f"sam2-job-{job_id}", "namespace": "sam2"},
    ...
}
api.create_namespaced_job(namespace="sam2", body=job_manifest)
```

**Notes**:
- PVCs use emptyDir by default for development. Update to PersistentVolumes backed by NFS, EBS, or local storage for production.
- GPU node pool required for SAM2 jobs (add `nodeSelector: accelerator: gpu` to job template).
- Cloudflare token goes in `CLOUDFLARED_TUNNEL_TOKEN` secret — create tunnel at https://dash.cloudflare.com/
- Update `secrets.env` with real R2/Supabase keys if using those services instead of MinIO.

