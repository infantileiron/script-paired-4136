"""数据库方言工具。

SQLite 仅用于本地开发与测试；生产使用 PostgreSQL，其行锁与咨询锁承担并发控制。
"""


def is_sqlite(session):
    bind = session.bind
    return bind is not None and bind.dialect.name == 'sqlite'
