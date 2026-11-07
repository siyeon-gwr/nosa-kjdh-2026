"""
scripts/nosa/r2util.py — 노사 산출물 R2 영구 저장/복원
Render 디스크는 재배포 시 초기화되므로, 분할·업로드 산출물은 R2에 박는다.
app.py의 R2 설정과 동일한 환경변수 사용.
"""
import os, json, io
import boto3
from botocore.client import Config

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_BUCKET = os.getenv("R2_BUCKET")
PREFIX = "nosa/"   # R2 안에서 노사 데이터 보관 경로


def _client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def save_json(name, obj):
    """dict/list를 R2에 JSON으로 저장. name 예: 'nosa_units.json'"""
    body = json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")
    _client().put_object(Bucket=R2_BUCKET, Key=PREFIX + name,
                         Body=body, ContentType="application/json")
    return f"r2://{R2_BUCKET}/{PREFIX}{name} ({len(body)} bytes)"


def load_json(name):
    """R2에서 JSON 읽기. 없으면 None."""
    try:
        obj = _client().get_object(Bucket=R2_BUCKET, Key=PREFIX + name)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except Exception:
        return None


def exists(name):
    try:
        _client().head_object(Bucket=R2_BUCKET, Key=PREFIX + name)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    # 연결 테스트
    print("R2_ACCOUNT_ID:", "OK" if R2_ACCOUNT_ID else "MISSING")
    print("R2_BUCKET:", R2_BUCKET or "MISSING")
    test = save_json("_r2_test.json", {"ok": True})
    print("저장 테스트:", test)
    print("복원 테스트:", load_json("_r2_test.json"))
