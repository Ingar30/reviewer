# Private Work Cloud test

Use this only in a task visibly running in **Work Cloud**, not a local or connected
computer session. This is a maintainer acceptance test, not proof of plugin installation.

## Prompt for the cloud task

Test Economics Paper Reviewer using only this task's OpenAI-hosted environment.
Do not access a local computer, Git checkout, existing paper review, or local Python
environment. Do not use API credentials, nested Codex processes, or a paid backend.

Use the installed Economics Paper Reviewer skill if it is available. Otherwise,
for this developer test only, I authorize use of the attached plugin ZIP as code
and instructions. Inspect its paths and file types before extracting to a new
cloud folder. Read `skills/review-paper/SKILL.md` and its required references in full.
The ZIP is a trusted build I supplied, not a review checkpoint or paper attachment.
Do not execute code from checkpoint archives. Running an attached bundle does not
mean the plugin is installed or discoverable; record that distinction.

First establish the execution host from actual task metadata or visible host
selection. If it cannot be established as OpenAI-hosted, stop. A Linux path or
successful Python command is insufficient evidence. Check the bundled coordinator's
doctor and the host's native subagent, file, page-image and web capabilities.
I authorize installation of the bundled pinned Python dependencies in a fresh,
isolated environment **inside this cloud task only**, if needed and permitted by
the host. Use the bundled preparation helper; do not alter global packages or
network/billing settings. Record its result. If required capabilities are missing,
return the specific blocker without substituting a local review.

Then review the attached **cloud-test-paper.pdf** in Full mode, following the
canonical skill and native orchestration procedure. This is a synthetic fixture,
not a real research paper. Keep the same routing, evidence and validation rules.
Use the host's included usage, subject to its actual limits; do not buy credits
or enable overages. Record observed model/effort only when available.

Deliver the complete downloadable PDF and a checkpoint. Also provide a short
acceptance record: installed skill versus attached bundle, plugin ZIP hash, host
evidence, Python/dependency check, native child activity, actual settings or unknown,
mode, completion status, and PDF/checkpoint download results. Mark user download
confirmation as pending until I confirm it. Preserve the checkpoint for a second
cloud task to test restoration. Do not claim scientific quality from this fixture.

## What this test does not establish

An attached-bundle run tests hosted execution, not installation, discovery or public
distribution. A full cloud acceptance pass still needs the installed plugin route,
user-confirmed PDF downloading, checkpoint restoration in another cloud task, and
representative real-paper quality testing. See `docs/chatgpt_work_plugin_acceptance.md`
in the canonical repository for the maintained acceptance cases.
