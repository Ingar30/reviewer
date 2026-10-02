# Model overrides

These commands are from this revision. See the checked-in configuration for its default.

```powershell
python scripts/review_paper.py --backend codex --pdf "inputs/my-paper.pdf"
```

```powershell
python scripts/review_paper.py --backend codex --pdf "inputs/my-paper.pdf" --model gpt-6-luna --reasoning-effort xhigh
```

```powershell
python scripts/review_paper.py --backend codex --model gpt-6.1-sol --reasoning-effort high --pdf "inputs/my-paper.pdf"
```

```powershell
python scripts/review_paper.py --backend codex --pdf "inputs/my-paper.pdf" --model gpt-5.6-terra --reasoning-effort xhigh
```

```powershell
python scripts/review_paper.py --pdf "inputs/my-paper.pdf" --model MODEL_ID --reasoning-effort EFFORT
```
