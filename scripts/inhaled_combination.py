"""Combination rules for inhaled therapy.

Rules implemented:
- ICS/LABA + LAMA allowed together.
- If any Triple selected, all other ICS/LABA or LAMA are invalidated (only Triple remains).

Provides `evaluate_selection(selected_names, master_path)` which returns list of active master rows.
"""
import csv
from pathlib import Path


def load_master(master_path: Path):
    m = []
    with master_path.open('r', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            m.append(r)
    return m


def evaluate_selection(selected_names, master_path: Path):
    """Given a list of selected master `drug_name` values, return effective list per rules.

    selected_names: list of strings matching `drug_name` in master (exact match expected)
    """
    master = load_master(master_path)
    # build lookup
    lookup = {r['drug_name']: r for r in master}
    selected = [lookup.get(n) for n in selected_names if lookup.get(n)]

    # if any Triple present, return only Triple entries (from selected)
    triples = [s for s in selected if s.get('class') == 'Triple']
    if triples:
        return triples

    # else allow ICS/LABA and LAMA together; filter only those classes and keep order
    allowed = [s for s in selected if s.get('class') in ('ICS/LABA', 'LAMA')]
    return allowed


if __name__ == '__main__':
    import sys
    repo = Path('.')
    master = repo / 'data' / 'inhaled_drug_master.csv'
    # example usage
    examples = [
        ['フルティフォーム 50μg', 'テリルジー 200'],
        ['フルティフォーム 50μg', 'アテキュラ 中用量'],
    ]
    for ex in examples:
        res = evaluate_selection(ex, master)
        print('Selection:', ex, '=> active:', [r['drug_name'] for r in res])
