const DEFAULT_BOT_LOGIN = "chatgpt-codex-connector[bot]";
const DEFAULT_CONTEXT = "Codex Review Gate";
const DEFAULT_POLL_INTERVAL_MS = 15_000;
const DEFAULT_TIMEOUT_MS = 8 * 60_000;

function findCodexSignal({
  reviews,
  reactions,
  headSha,
  triggeredAt,
  botLogin = DEFAULT_BOT_LOGIN,
}) {
  const review = reviews.find(
    (candidate) =>
      candidate.user?.login === botLogin &&
      candidate.commit_id === headSha &&
      candidate.state !== "DISMISSED",
  );

  if (review) {
    return { type: "review", createdAt: review.submitted_at };
  }

  const reaction = reactions.find(
    (candidate) =>
      candidate.user?.login === botLogin &&
      candidate.content === "+1" &&
      Date.parse(candidate.created_at) >= triggeredAt,
  );

  if (reaction) {
    return { type: "no-findings", createdAt: reaction.created_at };
  }

  return null;
}

async function run({ github, context, core }) {
  const pullRequest = context.payload.pull_request;
  if (!pullRequest) {
    throw new Error("Codex review gate requires a pull_request_target event");
  }

  const { owner, repo } = context.repo;
  const pullNumber = pullRequest.number;
  const headSha = pullRequest.head.sha;
  const statusContext = process.env.CODEX_STATUS_CONTEXT || DEFAULT_CONTEXT;
  const botLogin = process.env.CODEX_BOT_LOGIN || DEFAULT_BOT_LOGIN;
  const pollIntervalMs = Number(
    process.env.CODEX_POLL_INTERVAL_MS || DEFAULT_POLL_INTERVAL_MS,
  );
  const timeoutMs = Number(process.env.CODEX_TIMEOUT_MS || DEFAULT_TIMEOUT_MS);
  const eventTimestamp =
    Date.parse(pullRequest.updated_at || pullRequest.created_at) - 1_000;
  const deadline = Date.now() + timeoutMs;
  const targetUrl = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;

  const setStatus = (state, description) =>
    github.rest.repos.createCommitStatus({
      owner,
      repo,
      sha: headSha,
      state,
      context: statusContext,
      description,
      target_url: targetUrl,
    });

  await setStatus("pending", "Waiting for Codex App review");

  while (Date.now() < deadline) {
    const { data: currentPullRequest } = await github.rest.pulls.get({
      owner,
      repo,
      pull_number: pullNumber,
    });

    if (currentPullRequest.head.sha !== headSha) {
      core.info("PR head changed; a newer gate run will evaluate the new head");
      return;
    }

    if (currentPullRequest.state !== "open") {
      core.info("PR is no longer open; no merge gate is needed");
      return;
    }

    const [reviews, reactions] = await Promise.all([
      github.paginate(github.rest.pulls.listReviews, {
        owner,
        repo,
        pull_number: pullNumber,
        per_page: 100,
      }),
      github.paginate(github.rest.reactions.listForIssue, {
        owner,
        repo,
        issue_number: pullNumber,
        per_page: 100,
      }),
    ]);

    const signal = findCodexSignal({
      reviews,
      reactions,
      headSha,
      triggeredAt: eventTimestamp,
      botLogin,
    });

    if (signal) {
      const description =
        signal.type === "review"
          ? "Codex reviewed the current PR head"
          : "Codex reported no findings on this PR update";
      await setStatus("success", description);
      core.info(`${description} at ${signal.createdAt}`);
      core.setOutput("signal", signal.type);
      return;
    }

    core.info(`No completed Codex review signal yet; polling again in ${pollIntervalMs}ms`);
    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
  }

  await setStatus("failure", "Codex did not complete review within 8 minutes");
  core.setFailed(
    "Timed out waiting for Codex. Re-request review with '@codex review', then rerun this job.",
  );
}

module.exports = run;
module.exports.findCodexSignal = findCodexSignal;

