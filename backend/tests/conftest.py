import os
import shutil
import tempfile

# 必须在导入应用模块前配置环境（database/security 在导入时读取环境变量）
_TMP = tempfile.mkdtemp(prefix='anon-test-')
_ART = os.path.join(_TMP, 'artifacts')
os.environ.setdefault('JWT_SECRET', 'unit-test-secret-32bytes-minimum-0001')
os.environ.setdefault('DATABASE_URL', 'sqlite:///' + os.path.join(_TMP, 'test.db'))
os.environ.setdefault('REDIS_URL', '')  # 强制使用进程内 broker，测试不依赖 Redis
os.environ.setdefault('ARTIFACT_DIR', _ART)

import pytest  # noqa: E402

from src.config.database import Base, Session, engine  # noqa: E402
from src.models import entities as _entities  # noqa: E402  导入即注册全部 ORM 表
from src.services.broker import reset_broker  # noqa: E402

assert _entities is not None


@pytest.fixture()
def session():
    """每个测试一套全新的表、本地 broker 与干净产物目录。"""
    reset_broker()
    art = os.environ['ARTIFACT_DIR']
    if os.path.exists(art):
        shutil.rmtree(art)
    os.makedirs(art, exist_ok=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session() as s:
        yield s
    Base.metadata.drop_all(engine)


@pytest.fixture()
def artifact_dir():
    # ARTIFACT_DIR 在进程启动时固定为该临时目录，session fixture 已保证其干净
    d = os.environ['ARTIFACT_DIR']
    os.makedirs(d, exist_ok=True)
    return d

