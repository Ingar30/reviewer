# Economics Paper Reviewer: data and privacy

**Draft for publisher review; not yet an approved public policy.** Prepared
2026-09-09. This describes the repository implementation, not additional assurances
about OpenAI's services. The publisher must approve this page before submission.

## Where information goes

Economics Paper Reviewer is an open-source, skills-only package from
[Ingar30/reviewer](https://github.com/Ingar30/reviewer). There is no Reviewer-operated
inference backend, account system or telemetry endpoint in the package. Installing
it does not itself send a copy of your paper to the repository maintainer.

When you ask for a review, the host processes your uploaded PDF, extracted text,
tables, equations, rendered page images, review prompts, specialist findings and
final report. These are stored in the task's working files and made available to
the host's native review subagents. A local Codex host uses its local workspace;
a cloud-only review requires a genuinely hosted runtime, not a connected computer.
Use the host account's current terms, privacy policy and data controls to determine
retention, training use, access and deletion. This package does not override them
or guarantee confidentiality, a storage region or a retention period.

If web verification is available and enabled, review agents may search for cited
work or claims and open external sources. Queries can include manuscript-derived
text, titles, authors or reference details. Those requests are handled by the host's
web tools and the external services involved. For confidential material, consider
whether such searches are permitted; disabling search reduces verification and must
be disclosed in the report. No alternate external upload service is bundled.

If required Python packages are missing, the skill asks permission to install the
canonical dependencies into an isolated environment. Package installation contacts
package indexes/distribution services (normally PyPI and its file service); it does
not require an OpenAI API key or send the manuscript to the package index. Network
requests and dependencies remain subject to the host's controls and availability.

## Reports, checkpoints and support

Reports retain paper-derived quotations and findings. A checkpoint can contain the
original paper, extracted contents, images, prompts, reviews, reports and run state.
Treat both as confidential when the manuscript is confidential. Only share them
with people entitled to see the source paper; deleting a chat may not remove copies
you downloaded or shared. Manage working files, chat records and downloaded copies
through the respective host/device controls; the plugin has no remote deletion service.

The [GitHub issue tracker](https://github.com/Ingar30/reviewer/issues) is public.
Use it for non-sensitive bug reports with synthetic reproductions. Do not post
private manuscripts, credentials, personal data, unredacted diagnostics or checkpoint
archives. Anything you voluntarily post is handled by GitHub under its own terms
and may be visible to other people. The maintainer can see information you explicitly
share there, not your unshared host review sessions.

Review this page at each release if data flows or support arrangements change.
Adding a backend, telemetry, paid institutional service or new external processor
would require an explicit architectural and privacy review; none is promised here.
