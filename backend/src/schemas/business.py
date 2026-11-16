from pydantic import BaseModel,Field
from typing import Optional,Literal
class Login(BaseModel):email:str;password:str
class PairInput(BaseModel):
 code:str=Field(min_length=1,max_length=60)
 team:Literal['企业一组','企业二组']
 before:Optional[float]=Field(default=None,ge=0,le=100,allow_inf_nan=False)
 after:Optional[float]=Field(default=None,ge=0,le=100,allow_inf_nan=False)
 note:str=Field(default='',max_length=1000)
class EvaluationInput(BaseModel):
 name:str=Field(min_length=2,max_length=100)
 team:Literal['全部','企业一组','企业二组']='全部'
class AdoptionInput(BaseModel):
 evaluation_id:int=Field(gt=0)
 decision:Literal['继续试点','分组采纳','暂缓采纳']
 note:str=Field(min_length=8,max_length=2000)
class ReleaseInput(BaseModel):
 evaluation_id:int=Field(gt=0)
 name:str=Field(default='',max_length=120)
 lower:float=Field(allow_inf_nan=False)
 upper:float=Field(allow_inf_nan=False)
 epsilon:float=Field(gt=0,allow_inf_nan=False)
 def check_bounds(self):
  if self.upper<=self.lower:raise ValueError('裁剪上界必须严格大于下界')
  if self.epsilon<=0:raise ValueError('epsilon 必须为正数')
