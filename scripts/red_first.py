#!/usr/bin/env python3
"""Red first, reproducibly: every unit test is run against a deliberately
broken generator (or a planted fault in the data) and must FAIL there, and the
same test must PASS on an untouched copy.

For each mutant: copy the repo to a temp dir, apply the textual patch (each
`old` string must occur exactly once or the run aborts: a patch that does not
apply proves nothing), rebuild the data with the broken generator, then run
each named test on its own and require a non-zero exit. A generator that
crashes while building does not count as red: the mutant must build.

    python3 scripts/red_first.py            # all mutants
    python3 scripts/red_first.py NAME ...   # only these
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

T = "tests.test_"
DET = T + "determinism.Determinism."
STR = T + "structure."
SPL = T + "split."
LAB = T + "labels."

# name: (description, [(file, old, new), ...], [test ids that must fail], kind)
# kind "data" patches a data file after the build instead of the generator.
MUTANTS = {
    "unseeded-rng": (
        "rng_for ignores the seed and draws from the OS",
        [("gen/common.py", 'return random.Random(f"typryx-evalset|{seed}|{name}")', "return random.Random()")],
        [DET + "test_same_seed_same_bytes", DET + "test_same_bytes_under_different_hash_seeds"], "gen"),
    "hash-seeded-rng": (
        "rng_for mixes in hash(name), which PYTHONHASHSEED randomises",
        [("gen/common.py", 'return random.Random(f"typryx-evalset|{seed}|{name}")', "return random.Random(hash(name) + seed)")],
        [DET + "test_same_bytes_under_different_hash_seeds"], "gen"),
    "seed-ignored": (
        "rng_for drops the seed, so every seed gives the same data",
        [("gen/common.py", 'return random.Random(f"typryx-evalset|{seed}|{name}")', 'return random.Random(f"typryx-evalset||{name}")')],
        [DET + "test_a_different_seed_changes_the_data"], "gen"),
    "edited-data-file": (
        "one byte of data/train.jsonl changed after the build",
        [("data/train.jsonl", "request.complexity", "request.complexitY")],
        [DET + "test_data_on_disk_is_what_the_generator_writes"], "data"),
    "imbalanced-label": (
        "action.risk_class gets 101 financial rows",
        [("gen/action.py", "counts = spread(rng, per_label, gids)", "counts = spread(rng, per_label + (1 if lab == 'financial' else 0), gids)")],
        [STR + "Rows.test_balance_per_family_and_label", STR + "Rows.test_three_thousand_rows_five_hundred_per_family"], "gen"),
    "kind-imbalance": (
        "outcome_met: 'add' tasks get 22 true and 28 false",
        [("gen/outcome.py", "            trues[g] += 1\n", "            trues[g] += 1 if kind != 'add' else 0\n")],
        [STR + "Rows.test_outcome_met_is_balanced_per_task_kind"], "gen"),
    "invalid-gold": (
        "request.complexity emits the label 'moderate', which the template does not define",
        [("gen/complexity.py", "{\"prompt\": text}, lab, gid,", "{\"prompt\": text}, ('moderate' if lab == 'default' else lab), gid,")],
        [STR + "Rows.test_every_gold_is_valid_for_its_template"], "gen"),
    "two-distractors": (
        "a row gets a second extra state field",
        [("gen/common.py", "c.state[name] = rng.choice(DISTRACTORS[name])", "c.state[name] = rng.choice(DISTRACTORS[name]); c.state[name + '_2'] = 'x'")],
        [STR + "Rows.test_state_is_the_templates_fields_plus_at_most_one_distractor"], "gen"),
    "distractor-rate": (
        "half of all rows get a distractor",
        [("gen/common.py", "DISTRACTOR_RATE = 0.20", "DISTRACTOR_RATE = 0.50")],
        [STR + "Rows.test_distractor_rate_is_15_to_25_percent_overall_and_per_label"], "gen"),
    "distractor-tracks-label": (
        "distractors land mostly on true/level-0 rows: the overall rate stays in range, the per-label rate does not",
        [("gen/common.py", "k = round(DISTRACTOR_RATE * len(members))", "k = round((0.32 if key in ('true', '0') else 0.12) * len(members))")],
        [STR + "Rows.test_distractor_rate_is_15_to_25_percent_overall_and_per_label"], "gen"),
    "duplicate-ids": (
        "ids repeat after 400 rows",
        [("gen/common.py", 'f"{code}-{i:04d}"', 'f"{code}-{i % 400:04d}"')],
        [STR + "Rows.test_ids_are_unique"], "gen"),
    "too-few-groups": (
        "triage has only 12 rendering styles",
        [("gen/triage.py", "while len(styles) < 32:", "while len(styles) < 12:")],
        [STR + "Rows.test_at_least_twenty_groups_per_family_each_with_rows"], "gen"),
    "repeated-questions": (
        "console.question_topic no longer de-duplicates and draws the same text each time",
        [("gen/console.py", "text, slots = fill(rng.choice(forms), POOLS, rng)", "text, slots = fill(forms[0], POOLS, __import__('random').Random(1))"),
         ("gen/console.py", "                    if text not in seen:\n                        break", "                    if True:\n                        break")],
        [STR + "Rows.test_no_two_rows_in_a_family_ask_the_same_thing"], "gen"),
    "template-edited": (
        "a criteria string in a verbatim typryx template is reworded",
        [("templates/request.complexity.json", "a simple lookup", "a simple look-up")],
        [STR + "Templates.test_six_templates_exist_and_the_four_examples_are_verbatim"], "data"),
    "wide-dev-test": (
        "dev and test each take 30 percent of the groups",
        [("gen/common.py", "n_dev = n_test = max(1, int(0.15 * n + 0.5))", "n_dev = n_test = max(1, int(0.30 * n + 0.5))")],
        [SPL + "Split.test_proportions_are_about_70_15_15_per_family", SPL + "Splitter.test_the_split_is_about_70_15_15_by_groups"], "gen"),
    "split-by-row": (
        "rows are dealt to splits 70/15/15 by position, not by group",
        [("gen/build.py", 'lines[split_of[r["group"]]].append(line)',
          'lines[("train" if (len(lines["all"]) % 20) < 14 else "dev" if (len(lines["all"]) % 20) < 17 else "test")].append(line)')],
        [SPL + "Split.test_no_group_appears_in_two_splits", SPL + "Split.test_every_split_has_groups_it_alone_holds"], "gen"),
    "no-stratification": (
        "label-specific groups are pooled and not shuffled, so the dev and test files hold only the first labels",
        [("gen/build.py", "split_groups(rng_for(seed, mod.FAMILY + \"|split\"), mod.strata())",
          "split_groups(rng_for(seed, mod.FAMILY + \"|split\"), {'all': [g for gs in mod.strata().values() for g in gs]})"),
         ("gen/common.py", "        rng.shuffle(groups)\n", "        pass\n")],
        [SPL + "Split.test_every_label_appears_in_every_split"], "gen"),
    "splitter-accepts-tiny-strata": (
        "split_groups no longer refuses a stratum too small to split",
        [("gen/common.py", "if n - n_dev - n_test < 1:", "if False:")],
        [SPL + "Splitter.test_too_few_groups_refuse_rather_than_leak"], "gen"),
    "dominance-bar-lowered": (
        "triage: a cause wins at half the cost increase instead of three quarters",
        [("gen/triage.py", "DOM = 0.75", "DOM = 0.5")],
        [LAB + "Triage.test_generator_classifier_agrees_with_the_reference_on_a_sweep", LAB + "Triage.test_truth_table_holds_for_reference_and_generator",
         LAB + "Triage.test_a_dominant_cause_wins_even_when_a_second_cause_is_present"], "gen"),
    "second-cause-vetoes": (
        "triage: any second cause above 5 percent of the increase forces unknown (the old rule)",
        [("gen/triage.py", 'return w[0] if len(w) == 1 else "unknown"',
          'return w[0] if len(w) == 1 and sum(1 for v in shares(p).values() if v is not None and v > 0.05) == 1 else "unknown"')],
        [LAB + "Triage.test_a_dominant_cause_wins_even_when_a_second_cause_is_present", LAB + "Triage.test_truth_table_holds_for_reference_and_generator"], "gen"),
    "config-demands-traffic": (
        "triage: misconfiguration needs traffic known (the tri-0231 bug)",
        [("gen/triage.py", 's["config"] is not None and s["config"] >= DOM and e in SETTING_EVENTS:', 's["config"] is not None and s["config"] >= DOM and e in SETTING_EVENTS and p["traffic"] is not None:')],
        [LAB + "Triage.test_a_label_does_not_demand_evidence_its_own_verdict_does_not_need", LAB + "Triage.test_truth_table_holds_for_reference_and_generator"], "gen"),
    "bar-margin-removed": (
        "triage: rows may sit on the 3/4 bar",
        [("gen/triage.py", "MARGIN = 0.03", "MARGIN = 0.0")],
        [LAB + "Triage.test_every_share_is_clear_of_the_bar_so_no_row_turns_on_a_hair"], "gen"),
    "spend-unreconciled": (
        "triage: the headline spend drifts up to 15 points from what calls and price imply",
        [("gen/triage.py", 'p["spend"] = round(100 * ((1 + c / 100) * (1 + pr / 100) * cfg - 1))', 'p["spend"] = round(100 * ((1 + c / 100) * (1 + pr / 100) * cfg - 1)) + rng.randint(-15, 15)')],
        [LAB + "Triage.test_the_headline_spend_reconciles_with_the_shown_calls_and_price"], "gen"),
    "unknown-always-blank": (
        "every unknown scenario is a bare headline",
        [("gen/triage.py", 'flavour = rng.choice(["hidden", "hidden", "comparable", "comparable", "contradict", "contradict", "gray", "unreconciled", "blank"])', 'flavour = "blank"')],
        [LAB + "Triage.test_unknown_rows_come_in_the_three_flavours"], "gen"),
    "missing-item-is-level-2": (
        "quality: a level-2 answer omits an item instead of giving a vague one (the old wording)",
        [("gen/quality.py", "chosen = [bank[i][0] for i in order[:n - 1]] + [bank[order[n - 1]][1]]\n                        clear_n, vague_n = n - 1, 1\n                        rng.shuffle(chosen)",
          "chosen = [bank[i][0] for i in order[:n - 1]]\n                        clear_n, vague_n = n - 1, 0")],
        [LAB + "Quality.test_level_is_recomputed_from_the_text_by_counting_the_topics_facts", LAB + "Quality.test_a_missing_item_is_never_level_two"], "gen"),
    "level-rule-old-wording": (
        "quality.level_of scores N-1 clear items and nothing else as level 2",
        [("gen/quality.py", "    elif vague == 0 and 1 <= clear < n_asked:\n        return 1", "    elif vague == 0 and clear == n_asked - 1:\n        return 2\n    elif vague == 0 and 1 <= clear < n_asked:\n        return 1")],
        [LAB + "Quality.test_a_missing_item_is_never_level_two", LAB + "Quality.test_generator_parameters_give_the_same_level"], "gen"),
    "gray-zone-mislabelled": (
        "gray-zone scenarios are drawn but the row is labelled expected_growth",
        [("gen/triage.py", "cases.append(Case(FAMILY, TEMPLATE, {\"anomaly\": anomaly, \"recent_changes\": changes}, lab, sid, p))",
          "cases.append(Case(FAMILY, TEMPLATE, {\"anomaly\": anomaly, \"recent_changes\": changes}, ('expected_growth' if (lab == 'unknown' and p['traffic'] is not None and 10 < p['traffic'] < 20) else lab), sid, p))")],
        [LAB + "Triage.test_every_row_gold_is_the_label_of_its_parameters"], "gen"),
    "event-text-mismatch": (
        "the rendered change text names a cache change whatever the event parameter says",
        [("gen/triage.py", "text = rng.choice(EVENTS[p[\"event\"]])", "text = rng.choice(EVENTS['cache_disabled' if p['event'] == 'quota_raised' else p['event']])")],
        [LAB + "Triage.test_the_rendered_text_carries_what_the_parameters_say"], "gen"),
    "wrong-answer-labelled-true": (
        "a row labelled false states the right answer 10 percent of the time",
        [("gen/outcome.py", "given = right if is_right else near()", "given = right if (is_right or rng.random() < 0.1) else near()")],
        [LAB + "Outcome.test_near_misses_differ_from_the_right_answer", LAB + "Outcome.test_arithmetic_is_recomputed_from_the_text_alone"], "gen"),
    "multiplication-label-flipped": (
        "outcome_met stores the opposite gold for multiplication rows",
        [("gen/outcome.py", "{\"task\": task, \"final_answer\": final}, is_right, gid, p)", "{\"task\": task, \"final_answer\": final}, (is_right if kind != 'mul' else not is_right), gid, p)")],
        [LAB + "Outcome.test_arithmetic_is_recomputed_from_the_text_alone", LAB + "Outcome.test_every_kind_is_recomputed_from_its_parameters"], "gen"),
    "cue-free-reasoning": (
        "a reasoning template no longer asks for proof or steps",
        [("gen/complexity.py", '("Prove that {c}. Show every step of the argument.", {"c": CLAIMS}),', '("Show that {c} is true.", {"c": CLAIMS}),')],
        [LAB + "Complexity.test_reasoning_cue_if_and_only_if_reasoning"], "gen"),
    "cue-in-default": (
        "a default template picks up the word 'carefully'",
        [("gen/complexity.py", '("Give me a checklist for {a}.", {"a": CHECKLISTS}),', '("Carefully give me a checklist for {a}.", {"a": CHECKLISTS}),')],
        [LAB + "Complexity.test_reasoning_cue_if_and_only_if_reasoning"], "gen"),
    "length-tracks-level": (
        "padding removed, so short answers are the low levels",
        [("gen/quality.py", "while sum(len(x.split()) for x in parts) < target and pool:", "while False and pool:")],
        [LAB + "Quality.test_word_count_does_not_track_the_level"], "gen"),
    "delete-branch-mislabelled": (
        "github.delete_branch rows are labelled reversible_change",
        [("gen/action.py", "{\"tool\": tool, \"arguments\": arguments, \"target\": target}, lab, gid,",
          "{\"tool\": tool, \"arguments\": arguments, \"target\": target}, ('reversible_change' if tool == 'github.delete_branch' else lab), gid,")],
        [LAB + "Action.test_every_row_class_is_recomputed_from_the_call"], "gen"),
    "topic-word-in-wrong-list": (
        "a spend question is replaced by one about keys",
        [("gen/console.py", '"Which team is over budget right now?",', '"Which team owns the most keys right now?",')],
        [LAB + "Console.test_topic_vocabulary_matches_the_label_and_nothing_else"], "gen"),
    "row-source-wrong": (
        "rows claim source 'model' instead of 'construct'",
        [("gen/common.py", '"source": "construct",', '"source": "model",')],
        [STR + "Rows.test_row_keys_are_exactly_the_spec"], "gen"),
    "template-max-bytes": (
        "a template's max_state_bytes is halved",
        [("templates/action.risk_class.json", '"max_state_bytes": 16384', '"max_state_bytes": 8192')],
        [STR + "Templates.test_template_shape"], "data"),
    "manifest-count-edited": (
        "MANIFEST.json claims 499 rows for a family",
        [("data/MANIFEST.json", '"rows": 500', '"rows": 499')],
        [STR + "Rows.test_manifest_counts_agree_with_the_rows"], "data"),
    "dev-drops-a-row": (
        "one row never reaches any split file",
        [("gen/build.py", 'lines[split_of[r["group"]]].append(line)', 'lines[split_of[r["group"]]].append(line) if not r["id"].endswith("0007") else None')],
        [SPL + "Split.test_the_three_files_partition_all"], "gen"),
    "kind-coverage-lost": (
        "outcome_met groups are split with no task-kind stratum",
        [("gen/outcome.py", "return {k: groups_for(k) for k in KINDS}", 'return {"all": groups()}')],
        [SPL + "Split.test_every_task_kind_appears_in_dev_and_test"], "gen"),
    "splitter-drops-a-group": (
        "split_groups leaves the last train group unassigned (the tree is not rebuilt: the synthetic-strata test must see it alone)",
        [("gen/common.py", "for g in groups[n_dev + n_test:]:", "for g in groups[n_dev + n_test + 1:]:")],
        [SPL + "Splitter.test_a_group_is_assigned_once_and_every_group_is_assigned"], "gen-nobuild"),
    "long-cheap": (
        "a cheap template becomes a 65-word instruction",
        [("gen/complexity.py", '("Convert to uppercase: {t}", {"t": WORDS_UP}),',
          '("Convert the following text to uppercase exactly as typed, preserving every space, every punctuation mark and every line break in the original, and do not add, remove or reword anything else at all in your reply, and please do not wrap it in a code block or add any commentary before or after the converted text, just the text itself with nothing else around it, thank you very much: {t}", {"t": WORDS_UP}),')],
        [LAB + "Complexity.test_cheap_prompts_are_short_and_hard_prompts_are_not_one_liners"], "gen"),
    "task-omits-operand": (
        "an addition task states the first operand twice and never the second",
        [("gen/outcome.py", '"What is {a} + {b}?", "Add {a} and {b}."', '"What is {a} + {a}?", "Add {a} and {b}."')],
        [LAB + "Outcome.test_the_task_states_what_the_parameters_say"], "gen"),
    "reverse-near-miss-equals-right": (
        "a reverse-string near miss can be the right answer",
        [("gen/outcome.py", "cands = [w, right[:-1], right[1:]]", "cands = [right, right[:-1], right[1:]]"),
         ("gen/outcome.py", "cs = [c for c in candidates if c != right]", "cs = list(candidates)")],
        [LAB + "Outcome.test_near_misses_differ_from_the_right_answer", LAB + "Outcome.test_sort_and_reverse_near_misses_are_really_different_strings"], "gen"),
    "bank-overlap": (
        "a vague wording is a substring of its own clear wording",
        [("gen/quality.py", '("The vendor raised its per-token price", "Pricing is probably different now")', '("The vendor raised its per-token price", "The vendor raised its per-token")')],
        [LAB + "Quality.test_the_fact_banks_do_not_overlap"], "gen"),
    "params-clear-wrong": (
        "level-1 rows record one clear item more than they show",
        [("gen/quality.py", '"clear": clear_n, "vague"', '"clear": clear_n + (1 if level == 1 else 0), "vague"')],
        [LAB + "Quality.test_generator_parameters_give_the_same_level"], "gen"),
    "level-rule-lenient": (
        "level_of returns 1 for a build the spec does not define",
        [("gen/quality.py", 'raise ValueError(f"no level for asked={n_asked} clear={clear} vague={vague}")', "return 1")],
        [LAB + "Quality.test_level_rule_rejects_what_the_spec_does_not_define"], "gen"),
    "reference-verb-table-incomplete": (
        "(a fault in the TEST's own rule table) 'post' missing from the reversible verbs",
        [("tests/test_labels.py", '"cordon", "stop", "enable", "start", "post", "snooze"', '"cordon", "stop", "enable", "start", "snooze"')],
        [LAB + "Action.test_reference_rules_on_hand_cases", LAB + "Action.test_every_row_class_is_recomputed_from_the_call"], "gen-nobuild"),
    "action-group-names-collide": (
        "action groups no longer name their class and collide across classes",
        [("gen/action.py", 'return {lab: [f"{CODE}.{lab}.{i:02d}"', 'return {lab: [f"{CODE}.misc.{i:02d}"')],
        [LAB + "Action.test_group_carries_its_class"], "gen"),
    "complexity-group-names-collide": (
        "complexity groups no longer name their class",
        [("gen/complexity.py", 'return {lab: [f"{CODE}.{lab}.{i:02d}"', 'return {lab: [f"{CODE}.misc.{i:02d}"')],
        [LAB + "Complexity.test_group_carries_its_class"], "gen"),
    "console-group-names-collide": (
        "console groups no longer name their label",
        [("gen/console.py", 'return {lab: [f"{CODE}.{lab}.{i:02d}"', 'return {lab: [f"{CODE}.misc.{i:02d}"')],
        [LAB + "Console.test_group_carries_its_label"], "gen"),
}


def sh(cmd, cwd, **kw):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, **kw)


def copy_repo(dst: Path) -> None:
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns("__pycache__", ".git"))


def apply(tree: Path, patches) -> None:
    for rel, old, new in patches:
        p = tree / rel
        text = p.read_text()
        n = text.count(old)
        if n < 1 or (n > 1 and not rel.startswith("data/")):
            raise SystemExit(f"PATCH DOES NOT APPLY: {rel}: {old[:70]!r} occurs {n} times")
        p.write_text(text.replace(old, new, 1))


def first_failure(out: str) -> str:
    for line in out.splitlines():
        if line.startswith(("AssertionError", "ValueError", "KeyError", "RuntimeError")) or "Error:" in line:
            return line.strip()[:150]
    return "(non-zero exit)"


def main(argv: list[str]) -> int:
    names = argv or list(MUTANTS)
    unknown = [n for n in names if n not in MUTANTS]
    if unknown:
        print("unknown mutant:", unknown)
        return 2
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "clean"
        copy_repo(base)
        r = sh([PY, "-m", "gen.build"], base)
        if r.returncode:
            print("clean build failed:\n", r.stderr)
            return 1
        for name in names:
            desc, patches, tests, kind = MUTANTS[name]
            tree = Path(tmp) / name
            copy_repo(tree)
            if kind == "gen-nobuild":
                apply(tree, patches)
            elif kind == "gen":
                apply(tree, patches)
                b = sh([PY, "-m", "gen.build"], tree)
                if b.returncode:
                    print(f"NOT RED   {name}: the broken generator does not build: {first_failure(b.stderr)}")
                    bad += 1
                    continue
            else:
                b = sh([PY, "-m", "gen.build"], tree)
                apply(tree, patches)
            for t in tests:
                green = sh([PY, "-m", "unittest", t], base)
                red = sh([PY, "-m", "unittest", t], tree)
                ok = green.returncode == 0 and red.returncode != 0
                msg = first_failure(red.stderr) if red.returncode else "PASSED on the broken tree"
                print(f"{'RED -> GREEN' if ok else 'NOT RED    '}  {t.replace('tests.test_', '')}")
                print(f"              mutant {name}: {desc}")
                print(f"              broken: {msg}" if red.returncode else f"              {msg}")
                if not ok:
                    bad += 1
            shutil.rmtree(tree)
    print(f"\n{len(names)} mutants, {bad} not caught")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
