import difflib
f1='response_no_subsidy.html'
f2='response_with_subsidy.html'
try:
    a=open(f1,'r',encoding='utf-8').read().splitlines()
    b=open(f2,'r',encoding='utf-8').read().splitlines()
except Exception as e:
    print('ERR',e)
    raise
ud = difflib.unified_diff(a,b,fromfile=f1,tofile=f2,lineterm='')
count=0
for line in ud:
    print(line)
    count+=1
    if count>400:
        break
print('\n--done--')
