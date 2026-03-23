import json

def save_results(batch_num, results):
    output_path = "/home/jeanmfc/projects/ALEXIS/storage/snapshots/clinical_trials_v2/active_universe/llm_eval_results/task1/batch_%05d.json" % batch_num
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    relevant_count = sum(1 for r in results if r["relevant"])
    print("Batch %05d: Written %d results. Relevant: %d, Not relevant: %d" % (batch_num, len(results), relevant_count, len(results) - relevant_count))
print("script loaded")
