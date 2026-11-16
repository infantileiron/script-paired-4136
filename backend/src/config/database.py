import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
_url=os.environ['DATABASE_URL']
_is_sqlite=_url.startswith('sqlite')
# SQLite 仅用于本地/测试：允许跨线程连接并放宽锁等待，生产使用 PostgreSQL 行锁
_connect={'check_same_thread':False,'timeout':30} if _is_sqlite else {}
engine=create_engine(_url,pool_pre_ping=True,connect_args=_connect)
if _is_sqlite:
 @event.listens_for(engine,'connect')
 def _sqlite_pragma(dbapi_conn,_):
  # WAL + busy timeout：并发写在应用层分布式锁之外再由数据库串行，避免 database is locked
  cur=dbapi_conn.cursor()
  cur.execute('PRAGMA journal_mode=WAL')
  cur.execute('PRAGMA busy_timeout=30000')
  cur.execute('PRAGMA synchronous=NORMAL')
  cur.close()
Session=sessionmaker(bind=engine,expire_on_commit=False)
Base=declarative_base()
def db():
 with Session() as s: yield s
