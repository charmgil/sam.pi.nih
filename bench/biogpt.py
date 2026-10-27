"""BioGPT answers for Track B (runs in the bench/hf pixi environment, CPU).

BioGPT is a PubMed-pretrained causal LM without instruction tuning or a chat template, so it gets
the same prompt as the other models followed by "Answer:" and greedy generation. For multiple-choice
items it also records the option with the highest mean token log-likelihood (the usual way to
evaluate base LMs on MCQ), reported separately from the generated answer.

    python -I biogpt.py MODEL_DIR ITEMS.json ANSWERS.jsonl
"""

import json
import sys
import time
from pathlib import Path

import torch
from transformers import BioGptForCausalLM, BioGptTokenizer

model_dir, items_f, out_f = sys.argv[1:4]
torch.set_num_threads(16)
tok = BioGptTokenizer.from_pretrained(model_dir)
model = BioGptForCausalLM.from_pretrained(model_dir, torch_dtype=torch.float32).eval()
MAXPOS = model.config.max_position_embeddings
NEW = 150

done = set()
if Path(out_f).exists():
    done = {json.loads(line)["id"] for line in Path(out_f).read_text().splitlines()}


def ids_of(text: str, keep: int) -> torch.Tensor:
    ids = tok(text, return_tensors="pt").input_ids
    return ids[:, -keep:] if ids.shape[1] > keep else ids


@torch.no_grad()
def option_loglik(question: str, option: str) -> float:
    ctx = tok(f"Question: {question}\nAnswer:", return_tensors="pt").input_ids
    opt = tok(" " + option, add_special_tokens=False, return_tensors="pt").input_ids
    ids = torch.cat([ctx, opt], dim=1)[:, -MAXPOS:]
    logp = torch.log_softmax(model(ids).logits[0, :-1], dim=-1)
    n = opt.shape[1]
    tgt = ids[0, -n:]
    return logp[-n:].gather(1, tgt[:, None]).mean().item()


with open(out_f, "a") as fh:
    for it in json.loads(Path(items_f).read_text()):
        if it["id"] in done:
            continue
        t0 = time.time()
        ids = ids_of(it["prompt"] + "\nAnswer:", MAXPOS - NEW)
        with torch.no_grad():
            gen = model.generate(ids, max_new_tokens=NEW, do_sample=False, num_beams=1, no_repeat_ngram_size=3)
        new = gen[0, ids.shape[1]:]
        t_gen = time.time() - t0
        rec = {"id": it["id"], "answer": tok.decode(new, skip_special_tokens=True).strip(),
               "eval_count": int(new.shape[0]), "eval_s": round(t_gen, 2), "prompt_tokens": int(ids.shape[1])}
        if it["type"] == "mcq":
            ll = {k: option_loglik(it["question"], v) for k, v in it["options"].items()}
            rec["loglik_choice"] = max(ll, key=ll.get)
            rec["loglik"] = {k: round(v, 3) for k, v in ll.items()}
        rec["seconds"] = round(time.time() - t0, 1)
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
