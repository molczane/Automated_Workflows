"""Decide batch member states, verify outputs, and summarize observations."""

import re


def classify_member(context):
    if context['active_attempt']:
        return {'state': 'unresolved', 'reason': 'Execution is still recorded as active'}
    if context['verified_result']:
        return {'state': 'complete', 'reason': 'Output verified'}
    if context['validation_error']:
        return {'state': 'failed', 'reason': f"Input validation failed: {context['validation_error']}"}
    if context['missing_inputs']:
        roles = ', '.join(context['missing_inputs'])
        return {'state': 'blocked', 'reason': f'No verified location for input roles: {roles}'}
    last_attempt = context['last_attempt']
    if last_attempt and last_attempt['status'] == 'failed':
        return {'state': 'failed', 'reason': 'Investigate the previous failed application attempt'}
    if context['attempts_used'] >= context['max_attempts']:
        return {'state': 'failed', 'reason': 'Attempt budget exhausted'}
    if last_attempt and last_attempt['status'] == 'interrupted':
        return {'state': 'ready', 'reason': 'Interruption reconciled and attempt budget remains'}
    return {'state': 'ready', 'reason': 'Inputs verified and attempt budget remains'}


def verify_result(member, evidence):
    for key in ('request_id', 'attempt_id', 'artifact_id'):
        identifier = evidence.get(key)
        if not isinstance(identifier, str) or not identifier.strip():
            return False

    size = evidence.get('size_bytes')
    actual_size = evidence.get('actual_size_bytes')
    checksum = evidence.get('sha256')
    return (
        evidence['request_id'] == member.get('request_id')
        and type(size) is int and size > 0
        and type(actual_size) is int and actual_size == size
        and isinstance(checksum, str) and re.fullmatch(r'[0-9a-fA-F]{64}', checksum) is not None
        and evidence.get('actual_sha256') == checksum
        and all(evidence.get(flag) is True for flag in (
            'catalogue_link_verified', 'grid_verified', 'provenance_verified'
        ))
    )


def summarize_batch(rows):
    latest = {}
    for row in rows:
        member_id = row['member_id']
        previous = latest.get(member_id)
        if previous is None or row['observation_id'] > previous['observation_id']:
            latest[member_id] = row

    states = ('ready', 'complete', 'blocked', 'unresolved', 'failed', 'unobserved')
    members = {state: [] for state in states}
    for member_id in sorted(latest):
        state = latest[member_id]['state']
        members['unobserved' if state is None else state].append(member_id)
    counts = {state: len(ids) for state, ids in members.items()}
    return {'expected': len(latest), 'counts': counts, 'members': members}
