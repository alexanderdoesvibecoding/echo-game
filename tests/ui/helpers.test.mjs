/** Unit tests for API and HTML helper modules. */

import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";

import { installDom } from "./testDom.mjs";

const dom = installDom();
const { api } = await import("../../echo_adventure/ui/api.js");
const { $, escapeHtml } = await import("../../echo_adventure/ui/html.js");

beforeEach(() => {
  dom.reset();
  globalThis.fetch = undefined;
});

// Verifies api sends JSON headers, preserves options, and surfaces server errors.
test("api sends JSON headers, preserves options, and surfaces server errors", async () => {
  const calls = [];
  globalThis.fetch = async (path, options) => {
    calls.push({ path, options });
    return {
      ok: path === "/ok",
      /** Implement the json operation for this module. */
      async json() {
        return path === "/ok" ? { route: "ok" } : { error: "bad request" };
      },
    };
  };

  assert.deepEqual(await api("/ok", { method: "POST", body: "{}" }), { route: "ok" });
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.body, "{}");
  assert.equal(calls[0].options.headers["content-type"], "application/json");
  await assert.rejects(() => api("/bad"), /bad request/);
});

// Verifies html helpers locate elements and escape every unsafe character.
test("html helpers locate elements and escape every unsafe character", () => {
  dom.element("target").textContent = "found";

  assert.equal($("target").textContent, "found");
  assert.equal(escapeHtml(`<tag attr="x">&'`), "&lt;tag attr=&quot;x&quot;&gt;&amp;&#039;");
});
