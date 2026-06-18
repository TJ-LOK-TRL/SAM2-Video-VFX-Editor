import dill
from typing import Optional

import storage


class DataSaver:
    _PREFIX = 'stages/'

    @staticmethod
    def _key(stage_name: str) -> str:
        return f"{DataSaver._PREFIX}{stage_name}"

    @staticmethod
    def add_stage(stage_name: str, data: object) -> None:
        try:
            storage.put_bytes(storage.OUTPUTS_BUCKET, DataSaver._key(stage_name), dill.dumps(data))
        except Exception as e:
            raise Exception(f"Failed to save data: {str(e)}")

    @staticmethod
    def get_stage(stage_name: str) -> Optional[object]:
        try:
            return dill.loads(storage.get_bytes(storage.OUTPUTS_BUCKET, DataSaver._key(stage_name)))
        except Exception:
            return None

    @staticmethod
    def end_stage(stage_name: str) -> None:
        try:
            storage.delete_object(storage.OUTPUTS_BUCKET, DataSaver._key(stage_name))
        except Exception:
            pass

    @staticmethod
    def end_stages(stage_names) -> None:
        for stage_name in stage_names:
            DataSaver.end_stage(stage_name)
