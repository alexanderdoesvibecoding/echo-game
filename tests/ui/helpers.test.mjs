import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";

import { installDom } from "./testDom.mjs";

const dom = installDom();
const { api } = await import("../../echo_adventure/ui/api.js");
const { $, escapeHtml, fmtNum } = await import("../../echo_adventure/ui/html.js");
const { renderSubmarineImage, SUBMARINE_IMAGE_SRC } = await import("../../echo_adventure/ui/submarineVisual.js");

beforeEach(() => {
  dom.reset();
  globalThis.fetch = undefined;
});

test("api sends JSON headers, preserves options, and surfaces server errors", async () => {
  const calls = [];
  globalThis.fetch = async (path, options) => {
    calls.push({ path, options });
    return {
      ok: path === "/ok",
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

test("html helpers locate elements, escape every unsafe character, and format numbers", () => {
  dom.element("target").textContent = "found";

  assert.equal($("target").textContent, "found");
  assert.equal(escapeHtml(`<tag attr="x">&'`), "&lt;tag attr=&quot;x&quot;&gt;&amp;&#039;");
  assert.equal(fmtNum(1234.7), "1,235");
  assert.equal(fmtNum(null), "0");
});

test("submarine visual renders safe accessible and decorative variants", () => {
  assert.equal(SUBMARINE_IMAGE_SRC, "/ui/assets/virginia-submarine-cutout.png");
  const accessible = renderSubmarineImage({ idPrefix: `sub"&`, className: "hero", ariaLabel: `Sub "&` });
  assert.match(accessible, /alt="Sub &quot;&amp;"/);
  assert.match(accessible, /class="hero"/);
  assert.doesNotMatch(accessible, /id="sub"&/);

  const decorative = renderSubmarineImage({ decorative: true });
  assert.match(decorative, /alt="" aria-hidden="true"/);
});
