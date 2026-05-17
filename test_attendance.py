from classes.attendance import build_attendance_report

report = build_attendance_report("Grokenspiel")

print(f"\nAttendance Report for {report['player']}")
print(f"Cycle {report['cycle']} ({report['start_date']} to {report['end_date']})")
print(f"EP: {report['ep_earned']} / {report['ep_cap']}")
print(f"\nDiscrepancies found: {len(report['discrepancies'])}")

for d in report['discrepancies']:
    print(f"\n  {d['date']}  {d['event_type']}  {d['location']}")
    print(f"  Guild had:    {', '.join(d['guild_checkins'])}")
    print(f"  You received: {', '.join(d['player_got']) if d['player_got'] else 'nothing'}")
    print(f"  Missing:      {', '.join(d['missing'])}")