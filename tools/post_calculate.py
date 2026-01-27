import requests, re
url='http://127.0.0.1:5000/calculate'
form={
 'drug_id':'tezspire',
 'start_date':'2026-01-01',
 'qty2':'1',
 'qty3':'3',
 'system_version':'R7',
 'age_group':'under70',
 'income_category':'U',
 'burden_ratio':'0.3',
 'use_medical_deduction':'on',
 'taxable_income':'8000000',
 'use_subsidy':'on',
 'subsidy_cap':'30000',
}
print('POSTing to', url)
r=requests.post(url, data=form, timeout=20)
html=r.text
# Try to extract values
out={}
# annual_post_subsidy_self_pay: find label '付加給付調整後' then next ¥.../年
m=re.search(r'付加給付調整後.*?¥([0-9,]+)[^\d/\n]*?/年', html, re.S)
if m:
    out['annual_post_subsidy_self_pay']=m.group(1).replace(',','')
# medical total
m=re.search(r'医療費控除（還付） 合計：<strong>¥([0-9, ,]+)</strong>', html)
if m:
    out['medical_tax_refund_total']=m.group(1).replace(',','').replace(' ','')
# income tax line under calendar_start
m=re.search(r'所得税：\s*¥([0-9,]+)', html)
if m:
    out['medical_tax_refund_income']=m.group(1).replace(',','')
# resident tax
m2=re.search(r'住民税：\s*¥([0-9,]+)', html)
if m2:
    out['medical_tax_refund_resident']=m2.group(1).replace(',','')
# total_self_pay_annual (first occurrence under calendar_start)
# New UI label: 既存治療＋生物学的製剤（自己負担・年）
m3=re.search(r'既存治療＋生物学的製剤（自己負担・年）\s*</div>\s*<div style="font-size:1.1em">¥([0-9,]+)[^\d]*?/年', html, re.S)
if m3:
    out['total_self_pay_annual']=m3.group(1).replace(',','')
# existing_annual_post_subsidy - find the monthly post section for calendar_start and take that value
m4=re.search(r'付加給付調整後\s*</div>\s*<div style="font-size:1.1em">¥([0-9,]+)[^\d]*?/年', html, re.S)
if m4:
    out['annual_post_subsidy_self_pay_from2']=m4.group(1).replace(',','')
# existing_final_annual: find '既存治療' under calendar_start and its value
m5=re.search(r'<strong>① .*?年度</strong>.*?既存治療\s*</div>\s*<div style="font-size:1.1em">¥([0-9,]+)[^\d]*?/年', html, re.S)
if m5:
    out['existing_annual']=m5.group(1).replace(',','')
# difference_subsidy_after_medical: find '差額（付加給付後）' or medical diff
m6=re.search(r'差額（付加給付後）\s*</div>\s*<div style="font-size:1.1em">¥([0-9,\-]+)[^\d]*?/年', html, re.S)
if m6:
    out['difference_subsidy_after_medical']=m6.group(1).replace(',','')

# If some keys missing, print whole calendar_start block
if len(out) < 8:
    mblk=re.search(r'<div class="card">\s*<strong>① .*?年度</strong>(.*?)</div>\s*</div>', html, re.S)
    if mblk:
        print('--- calendar_start block ---')
        print(mblk.group(1))
    else:
        print('Could not extract calendar_start block; dumping full response length:', len(html))
    print('\n--- extracted keys so far ---')
    for k,v in out.items():
        print(k+':', v)
else:
    for k,v in out.items():
        print(k+':', v)

# Verify prescription schedule sum for calendar_start year
sched_sum = 0
try:
    import datetime as _dt
    mtable = re.search(r'<h3>処方スケジュール.*?<table.*?>(.*?)</table>', html, re.S)
    if mtable:
        table_html = mtable.group(1)
        # headers
        headers = re.findall(r'<th[^>]*>(.*?)</th>', table_html, re.S)
        # find column index for date and for self-pay (自己負担)
        date_idx = None
        pay_idx = None
        for i, h in enumerate(headers):
            th = re.sub(r'<.*?>', '', h).strip()
            if ('日付' in th) or ('date' in th.lower()) or ('投与日' in th) or ('開始日' in th) or ('投与日' in th):
                date_idx = i
            if ('自己負担' in th) or ('自己負担金額' in th) or ('自己負担（円）' in th):
                pay_idx = i
        # rows
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.S)
        for rrow in rows[1:]:
            cols = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', rrow, re.S)
            if not cols:
                continue
            # extract date
            dstr = None
            if date_idx is not None and date_idx < len(cols):
                d_raw = re.sub(r'<.*?>', '', cols[date_idx]).strip()
                mdate = re.search(r'(\d{4}-\d{2}-\d{2})', d_raw)
                if mdate:
                    dstr = mdate.group(1)
            else:
                # try to find any date in row
                mdate = re.search(r'(\d{4}-\d{2}-\d{2})', rrow)
                if mdate:
                    dstr = mdate.group(1)
            # extract pay
            pay_val = None
            if pay_idx is not None and pay_idx < len(cols):
                pay_raw = re.sub(r'<.*?>', '', cols[pay_idx]).strip()
                mp = re.search(r'¥?\s*([0-9,\-]+)', pay_raw)
                if mp:
                    pay_val = int(mp.group(1).replace(',', '').replace('-', '0') or 0)
            else:
                # try to find yen amounts in row and take last one
                mps = re.findall(r'¥\s*([0-9,\-]+)', rrow)
                if mps:
                    pay_val = int(mps[-1].replace(',', '').replace('-', '0') or 0)
            if dstr and pay_val is not None:
                try:
                    dy = int(dstr.split('-')[0])
                    if dy == 2026:
                        sched_sum += int(pay_val)
                except Exception:
                    pass
except Exception:
    sched_sum = None

print('prescription_schedule_sum_for_2026:', sched_sum)
