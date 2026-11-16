"""Redis 队列与分布式预算锁的薄封装。

生产环境使用 Redis（跨进程互斥、持久化队列）；本地开发或单元测试没有 Redis 时，
退化为进程内 FIFO 队列与线程锁，行为契约保持一致，业务代码不感知差异。
"""
import os
import threading
import time
from collections import deque

try:
 import redis as _redis
except Exception:  # pragma: no cover - 极端环境无 redis 包
 _redis=None

EVAL_QUEUE='paired:evaluations'
RELEASE_QUEUE='paired:releases'
BUDGET_LOCK='paired:budget-lock'
_LOCK_TTL=30  # 秒，worker 崩溃后锁自动释放，可被恢复任务重新获取


class _LocalBroker:
 def __init__(self):
  self._q=deque();self._cond=threading.Condition();self._lock=threading.Lock();self._token=0
 def rpush(self,key,value):
  with self._cond:
   self._q.append((key,str(value)));self._cond.notify()
 def blpop(self,key,timeout=3):
  deadline=time.time()+timeout
  with self._cond:
   while not any(k==key for k,_ in self._q):
    remain=deadline-time.time()
    if remain<=0:return None
    self._cond.wait(timeout=remain)
  for idx,(k,v) in enumerate(self._q):
   if k==key:del self._q[idx];return (key,v)
  return None
 def acquire_lock(self,name,ttl=_LOCK_TTL):
  if self._lock.acquire(blocking=False):
   self._token+=1;return str(self._token)
  return None
 def release_lock(self,name,token):
  try:self._lock.release()
  except RuntimeError:pass
 def ping(self):return True


class _RedisBroker:
 def __init__(self,url):
  self._r=_redis.Redis.from_url(url)
 def rpush(self,key,value):self._r.rpush(key,value)
 def blpop(self,key,timeout=3):
  item=self._r.blpop(key,timeout=timeout)
  return item
 def acquire_lock(self,name,ttl=_LOCK_TTL):
  # SET NX PX：拿到才返回 token，持有者崩溃后 TTL 到期自动释放
  token=os.urandom(16).hex()
  if self._r.set(name,token,nx=True,px=int(ttl*1000)):return token
  return None
 def release_lock(self,name,token):
  # 仅允许持有者释放，用 Lua 保证比对与删除原子
  lua="if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"
  self._r.eval(lua,1,name,token)
 def ping(self):self._r.ping();return True


_broker=None
_broker_lock=threading.Lock()


def broker():
 """返回进程级单例 broker；REDIS_URL 不可达时回退本地实现。"""
 global _broker
 if _broker is not None:return _broker
 with _broker_lock:
  if _broker is not None:return _broker
  url=os.environ.get('REDIS_URL')
  if url and _redis is not None:
   try:
    b=_RedisBroker(url);b.ping();_broker=b;return _broker
   except Exception:pass
  _broker=_LocalBroker()
 return _broker


def reset_broker():
 """测试专用：清空单例，强制重新解析环境。"""
 global _broker
 with _broker_lock:_broker=None
