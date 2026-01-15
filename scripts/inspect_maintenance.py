from datetime import date
from src.biologic_schedule import generate_prescription_schedule, extend_maintenance_schedule

evs = generate_prescription_schedule('dupixent', date(2026,1,1), 1,1)
print('initial events:', evs)
maint = extend_maintenance_schedule(evs, 'dupixent', date(2026,10,10))
print('maintenance events:')
for m in maint:
    print(m)
