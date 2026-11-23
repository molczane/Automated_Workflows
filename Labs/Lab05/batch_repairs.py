"""These functions run, but their decisions need repair. Read SCHEMA_CONTRACT.md."""

def classify_member(context):
    # This succeeds for a simple fresh job but mishandles existing results and dependencies.
    if context['attempts_used'] >= context['max_attempts']:
        return {'state':'failed','reason':'Attempt budget exhausted'}
    if context['missing_inputs']:
        return {'state':'failed','reason':'Input missing'}
    if context['active_attempt']:
        return {'state':'unresolved','reason':'Execution is still recorded as active'}
    if context['verified_result']:
        return {'state':'complete','reason':'Output verified'}
    return {'state':'ready','reason':'Try the job'}

def verify_result(member,evidence):
    # A valid artifact ID is necessary. Is it enough evidence for this request?
    return bool(evidence.get('artifact_id'))

def summarize_batch(rows):
    # This works when every member has exactly one observation. Investigate repeated joins.
    counts={s:0 for s in ('ready','complete','blocked','unresolved','failed','unobserved')}
    members={s:[] for s in counts}
    for row in rows:
        if row['state'] is None:
            continue
        counts[row['state']]+=1
        members[row['state']].append(row['member_id'])
    return {'expected':sum(counts.values()),'counts':counts,'members':members}
