"""Inspect a local translation queue without mistaking an empty batch for completion."""
import argparse
import json
from pathlib import Path


def inventory(directory):
    root = Path(directory)
    pending, invalid = [], []
    requests = sorted(root.glob('*.request.json'), key=lambda p: (p.stat().st_mtime_ns, p.name))
    for request in requests:
        response = request.with_name(request.name.replace('.request.json', '.response.json'))
        if not response.exists():
            pending.append(request)
            continue
        try:
            data = json.loads(response.read_text(encoding='utf-8-sig'))
            if not isinstance(data, dict) or not isinstance(data.get('text'), str) or not data['text'].strip():
                raise ValueError('Expected nonempty text')
        except (OSError, ValueError):
            invalid.append(request)
    return requests, pending, invalid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--summary', action='store_true')
    parser.add_argument('--limit', type=int, default=3)
    args = parser.parse_args()
    if not args.directory.is_dir():
        parser.error('Queue directory does not exist; use the exact printed path')
    if args.limit < 1:
        parser.error('--limit must be positive')
    requests, pending, invalid = inventory(args.directory)
    state_file = args.directory / 'run-state.json'
    state = json.loads(state_file.read_text(encoding='utf-8')) if state_file.exists() else {'state': 'unknown'}
    print(json.dumps({'run': state, 'queue_requests': len(requests), 'pending': len(pending),
                      'invalid_responses': [p.name for p in invalid],
                      'note': 'Queue inventory includes reused files. Empty queue does not mean completion; check live engine and review PDFs.'}, ensure_ascii=False))
    if not args.summary:
        for request in pending[:args.limit]:
            data = json.loads(request.read_text(encoding='utf-8'))
            messages = data.get('messages', [])
            # Structured translation prompts repeat shared instructions; emit only this batch's input.
            content = messages[-1].get('content', '') if messages else ''
            if isinstance(content, str) and '## Here is the input:' in content:
                content = content.split('## Here is the input:', 1)[1].strip()
            print(json.dumps({'request': str(request), 'language': data.get('language'), 'input': content}, ensure_ascii=False))


if __name__ == '__main__':
    main()
