"""Fresh, bounded parent-availability reads using the caller's database client.

No cross-update cache: disabling a stage/subject must invalidate old keyboards.
Errors propagate so callers can reject access without returning partial results.
"""


def active_stages(database, stage_ids):
    ids = list({str(value): value for value in stage_ids if value is not None}.values())
    if not ids:
        return {}
    query = database.table('stages').select('id, stage_number, is_active')
    query = query.eq('id', ids[0]) if len(ids) == 1 else query.in_('id', ids)
    rows = query.eq('is_active', True).limit(len(ids)).execute().data or []
    return {str(row['id']): row for row in rows if row.get('is_active') is True}


def active_subjects(database, subject_ids):
    ids = list({str(value): value for value in subject_ids if value is not None}.values())
    if not ids:
        return {}
    query = database.table('subjects').select('id, name, description, stage_id')
    query = query.eq('id', ids[0]) if len(ids) == 1 else query.in_('id', ids)
    rows = query.eq('is_active', True).limit(len(ids)).execute().data or []
    stages = active_stages(database, [row.get('stage_id') for row in rows])
    return {str(row['id']): row for row in rows if str(row.get('stage_id')) in stages}


def active_subject(database, subject_id):
    return active_subjects(database, [subject_id]).get(str(subject_id))
