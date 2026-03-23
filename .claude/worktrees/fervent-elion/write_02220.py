import json,os
r=lambda nct,rel,rsn,tgts=None,novel=None:{"nct_id":nct,"relevant":rel,"reasoning":rsn,"targets":tgts or [],"novel_targets":novel or []}
T=lambda t,role,ev:{"target":t,"role":role,"result_use":"bioanalytical","safety_lab":False,"evidence":ev}
N=lambda n,role,ev:{"name":n,"role":role,"result_use":"bioanalytical","evidence":ev}
res=[]