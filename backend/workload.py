"""Employee working time: union of reservations, excluding planned lunch."""
from collections import defaultdict
from datetime import datetime


def merged(intervals):
    result = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def working_intervals(booking, event):
    intervals = [(booking.start, booking.end)]
    for task in event.data.get('plan', {}).get('tasks', []):
        if task['name'] != 'Обед':
            continue
        a, z = datetime.fromisoformat(task['start']), datetime.fromisoformat(task['end'])
        if z <= a:
            continue
        pieces = []
        for start, end in intervals:
            if z <= start or a >= end:
                pieces.append((start, end))
            else:
                if start < a: pieces.append((start, a))
                if z < end: pieces.append((z, end))
        intervals = pieces
    return intervals


def hours(intervals):
    return sum((end-start).total_seconds()/3600 for start, end in merged(intervals))


def employee_workload(resources, bookings, events):
    intervals = defaultdict(list)
    for booking in bookings:
        person = resources.get(booking.resource_id)
        event = events.get(booking.event_id)
        if not person or person.kind != 'Person' or not event or event.status == 'Cancelled':
            continue
        intervals[person.id].extend(working_intervals(booking, event))
    individual = {rid: hours(value) for rid, value in intervals.items()}
    departments = defaultdict(list)
    for rid in individual:
        departments[resources[rid].department].append(rid)
    stats = {}
    for department, people in departments.items():
        total = sum(individual[rid] for rid in people)
        stats[department] = {
            'people': len(people), 'average_hours': round(total/len(people), 1),
            'person_hours': round(total, 1),
            'busy_hours': round(hours([interval for rid in people for interval in intervals[rid]]), 1),
        }
    return individual, stats
