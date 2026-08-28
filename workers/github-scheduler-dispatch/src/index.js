const OWNER = "mr-romel";
const REPO = "khyrat-legal-content-engine";
const WORKFLOW = "publish-scheduled.yml";
const REF = "main";

export default {
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(dispatch(env));
  },

  async fetch(_request, env, ctx) {
    ctx.waitUntil(dispatch(env));
    return new Response("scheduler-dispatch: accepted\n", { status: 202 });
  },
};

async function dispatch(env) {
  if (!env.GITHUB_DISPATCH_TOKEN) throw new Error("GITHUB_DISPATCH_TOKEN is missing");

  const response = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "khyrat-github-scheduler-dispatch",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: REF }),
    },
  );

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`GitHub dispatch failed: ${response.status} ${body.slice(0, 500)}`);
  }
}
