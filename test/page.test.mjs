// test/page.test.mjs — executes index.html in jsdom and asserts real behaviour.
//
//   npm install --no-save jsdom
//   node test/page.test.mjs
//
// Exits non-zero on the first failed check.

import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

// Source-of-truth data the build embedded, parsed independently of the page.
const SOURCE = JSON.parse(
  html.match(/<script id="docs-data" type="application\/json">([\s\S]*?)<\/script>/)[1],
);
const src = Object.fromEntries(SOURCE.map((d) => [d.lang, d]));
const FULL_LEN = { en: src.en.raw.length, pl: src.pl.raw.length };
const H2_COUNT = {
  en: (src.en.raw.match(/^##\s/gm) || []).length,
  pl: (src.pl.raw.match(/^##\s/gm) || []).length,
};
const H3_COUNT = {
  en: (src.en.raw.match(/^###\s/gm) || []).length,
  pl: (src.pl.raw.match(/^###\s/gm) || []).length,
};
const TABLE_COUNT = {
  en: (src.en.raw.match(/^\|[-\s:|]+\|\s*$/gm) || []).length,
  pl: (src.pl.raw.match(/^\|[-\s:|]+\|\s*$/gm) || []).length,
};
const FENCE_COUNT = {
  en: (src.en.raw.match(/^```/gm) || []).length / 2,
  pl: (src.pl.raw.match(/^```/gm) || []).length / 2,
};

let failures = 0;
const check = (name, cond, detail = "") => {
  if (cond) console.log(`  ok   ${name}${detail ? ` — ${detail}` : ""}`);
  else {
    failures++;
    console.error(`  FAIL ${name}${detail ? ` — ${detail}` : ""}`);
  }
};

// ---- stubs jsdom lacks ----------------------------------------------------
const clipboardLog = [];
const downloads = [];
const observed = [];
const warnings = [];

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  pretendToBeVisual: true,
  url: "http://localhost/",
  beforeParse(window) {
    window.IntersectionObserver = class {
      constructor(cb) { this.cb = cb; observed.push(this); }
      observe(el) { (this.targets ||= []).push(el); }
      disconnect() {}
      unobserve() {}
    };
    window.isSecureContext = true;
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText: (t) => { clipboardLog.push(t); return Promise.resolve(); } },
      configurable: true,
    });
    window.URL.createObjectURL = () => "blob:mock";
    window.URL.revokeObjectURL = () => {};
    window.HTMLAnchorElement.prototype.click = function () { downloads.push(this.download); };
    window.scrollTo = () => {};
    window.Element.prototype.scrollIntoView = () => {};
    const realWarn = window.console.warn;
    window.console.warn = (...a) => { warnings.push(a.join(" ")); realWarn(...a); };
  },
});

const { window } = dom;
const { document } = window;
const errors = [];
window.addEventListener("error", (e) => errors.push(e.message));
const settle = (ms = 40) => new Promise((r) => setTimeout(r, ms));

const doc = document.getElementById("doc");
const h2s = () => [...doc.querySelectorAll("h2")];
const secBtns = () => [...doc.querySelectorAll("h2 button.copy-mini")];

/** Click the i-th section button and return what landed on the clipboard. */
async function copySection(i) {
  clipboardLog.length = 0;
  secBtns()[i].click();
  await settle(8);
  return clipboardLog[0] || "";
}

/**
 * Assert every section button copies *its own* slice — starts with "## ",
 * contains its own heading, and is a fraction of the full document rather than
 * a silent fallback to the whole file.
 */
async function assertAllSections(lang) {
  const btns = secBtns();
  const bad = [];
  for (let i = 0; i < btns.length; i++) {
    const heading = h2s()[i].textContent.replace("Kopiuj część", "").trim();
    const text = await copySection(i);
    if (!text.startsWith("## ")) bad.push(`${heading.slice(0, 26)} → not a "## " start`);
    else if (!text.includes(heading.slice(0, 16))) bad.push(`${heading.slice(0, 26)} → wrong slice`);
    else if (text.length >= FULL_LEN[lang] * 0.6) bad.push(`${heading.slice(0, 26)} → whole doc`);
  }
  check(
    `all ${btns.length} ${lang.toUpperCase()} sections copy their own markdown`,
    bad.length === 0,
    bad.join(" | ") || "all slices correct",
  );
  check(`no unmapped-section warning for ${lang.toUpperCase()}`, warnings.length === 0,
    warnings.join(" | ") || "none");
}

await settle(80);

console.log("\n— build integrity —");
check("no unreplaced build placeholders", !/@@[A-Z_]+@@/.test(document.body.textContent));
check("build.py section count matches rendered h2 (EN)",
  H2_COUNT.en === h2s().length, `source ${H2_COUNT.en} vs rendered ${h2s().length}`);
check("sectionText map covers every EN heading",
  Object.keys(src.en.sectionText).length === H2_COUNT.en,
  `${Object.keys(src.en.sectionText).length} mapped`);
check("sectionText map covers every PL heading",
  Object.keys(src.pl.sectionText).length === H2_COUNT.pl,
  `${Object.keys(src.pl.sectionText).length} mapped`);

console.log("\n— initial render —");
check("no uncaught JS errors", errors.length === 0, errors.join("; ") || "clean");
check("document body rendered", doc.innerHTML.length > 20000, `${doc.innerHTML.length} chars`);
check("top-level sections present", h2s().length === H2_COUNT.en, `${h2s().length} h2`);
check("subsections present", doc.querySelectorAll("h3").length === H3_COUNT.en,
  `${doc.querySelectorAll("h3").length} h3`);
check("tables rendered", doc.querySelectorAll("table").length === TABLE_COUNT.en,
  `${doc.querySelectorAll("table").length} tables`);
check("code blocks rendered", doc.querySelectorAll(".codeblock").length === FENCE_COUNT.en,
  `${doc.querySelectorAll(".codeblock").length} blocks`);
check("no raw markdown leaked into the DOM", !/(^|\n)#{2,4}\s/.test(doc.textContent));

console.log("\n— table of contents —");
const tocEl = document.getElementById("toc");
const tocLinks = [...tocEl.querySelectorAll("a")];
check("TOC built", tocLinks.length === H2_COUNT.en + H3_COUNT.en, `${tocLinks.length} links`);
check("every TOC link resolves to a real id",
  tocLinks.every((a) => document.getElementById(a.getAttribute("href").slice(1))));
check("scrollspy observer registered", observed.length === 1);
check("scrollspy observes every heading",
  observed[0] && observed[0].targets.length === H2_COUNT.en + H3_COUNT.en,
  `${observed[0]?.targets.length ?? 0} observed`);

console.log("\n— per-section copy (EN) —");
check("one copy button per section", secBtns().length === h2s().length,
  `${secBtns().length} buttons`);
const partI = await copySection(1);
check("copied text is the PART I markdown", partI.startsWith("## PART I"),
  JSON.stringify(partI.slice(0, 22)));
check("copied section stops before PART II", !partI.includes("## PART II"));
check("copied section keeps its body", partI.includes("Seven-Phase Reasoning Loop"));
check("copied section is a slice, not the whole file",
  partI.length < FULL_LEN.en * 0.5, `${partI.length} of ${FULL_LEN.en} chars`);
await assertAllSections("en");

console.log("\n— copy whole prompt —");
document.getElementById("copyAll").click();
await settle(20);
const full = clipboardLog.at(-1) || "";
check("whole prompt is the full EN markdown", full === src.en.raw,
  `${full.length} chars`);
check("whole prompt includes the LITE appendix", full.includes("APPENDIX B"));

console.log("\n— code block copy —");
doc.querySelector("[data-copy-code]").click();
await settle(20);
check("LITE block copies its code", (clipboardLog.at(-1) || "").includes("You are a reasoning engine"),
  JSON.stringify((clipboardLog.at(-1) || "").slice(0, 38)));

console.log("\n— search —");
const q = document.getElementById("q");
const hits = document.getElementById("hits");
q.value = "hallucination";
q.dispatchEvent(new window.Event("input"));
await settle(420);
check("search highlights matches", doc.querySelectorAll("mark").length === 4,
  `${doc.querySelectorAll("mark").length} <mark>`);
check("hit counter updated", hits.textContent === "4 trafień", `"${hits.textContent}"`);

q.value = "zzzzqqqq";
q.dispatchEvent(new window.Event("input"));
await settle(420);
check("no-match reports zero",
  doc.querySelectorAll("mark").length === 0 && hits.textContent === "brak",
  `"${hits.textContent}"`);

q.value = "";
q.dispatchEvent(new window.Event("input"));
await settle(420);
check("clearing the query restores clean DOM", doc.querySelectorAll("mark").length === 0);

console.log("\n— language switch —");
document.querySelector('.seg button[data-lang="pl"]').click();
await settle(60);
check("PL content rendered", doc.textContent.includes("DYREKTYWA GŁÓWNA"));
check("EN content gone", !doc.textContent.includes("PRIME DIRECTIVE"));
check("PL sections rendered", h2s().length === H2_COUNT.pl, `${h2s().length} h2`);
check("PL TOC rebuilt", document.querySelectorAll("#toc a").length === H2_COUNT.pl + H3_COUNT.pl,
  `${document.querySelectorAll("#toc a").length} links`);
check("html lang updated", document.documentElement.lang === "pl");
await assertAllSections("pl");

console.log("\n— download —");
document.getElementById("dlMd").click();
check("download uses the active language", downloads.at(-1) === "OMNICOGNITION-5.0-PL.md",
  downloads.at(-1));
document.querySelector('.seg button[data-lang="en"]').click();
await settle(60);
document.getElementById("dlTxt").click();
check("download follows the switch back to EN", downloads.at(-1) === "OMNICOGNITION-5.0-EN.txt",
  downloads.at(-1));
check("switching back restores EN content", doc.textContent.includes("PRIME DIRECTIVE"));

console.log("\n— variant buttons —");
const vbtns = [...document.querySelectorAll(".vbtn")];
check("EN exposes both variants", vbtns.length === Object.keys(src.en.variants).length,
  `${vbtns.length} buttons: ${Object.keys(src.en.variants).join(", ")}`);
vbtns[0].click();
await settle(20);
check("LITE button copies the LITE variant",
  clipboardLog.at(-1) === src.en.variants.LITE,
  `${(clipboardLog.at(-1) || "").length} chars`);
// A <=3B model typically has a 4k-8k context. The system prompt must leave the
// bulk of that for the actual task, so LITE is budgeted at <500 tokens (~2000
// chars) rather than some rounder number.
check("LITE variant fits a small model's budget (<500 tokens)",
  src.en.variants.LITE.length < 2000,
  `${src.en.variants.LITE.length} chars ≈ ${Math.round(src.en.variants.LITE.length / 4)} tokens`);
check("one-line variant really is one line",
  src.en.variants.ONELINE.trim().split("\n").length === 1,
  `${src.en.variants.ONELINE.trim().length} chars`);
check("LITE variant is self-contained (has its own rules)",
  /\n1[0-4]\./.test(src.en.variants.LITE), "numbered rules present");

console.log("\n— permalink anchors —");
const anchors = [...doc.querySelectorAll("h2[id] .anchor, h3[id] .anchor")];
check("every heading has an anchor",
  anchors.length === H2_COUNT.en + H3_COUNT.en, `${anchors.length} anchors`);
check("anchors point at real ids",
  anchors.every((a) => document.getElementById(a.getAttribute("href").slice(1))));

console.log("\n— mobile TOC drawer —");
const aside = document.getElementById("aside");
const scrim = document.getElementById("scrim");
const toggle = document.getElementById("tocToggle");
check("drawer starts closed", !aside.classList.contains("open"));
toggle.click();
check("toggle opens the drawer",
  aside.classList.contains("open") && scrim.classList.contains("open")
  && toggle.getAttribute("aria-expanded") === "true");
document.getElementById("tocClose").click();
check("close button closes it", !aside.classList.contains("open") && !scrim.classList.contains("open"));
toggle.click();
scrim.click();
check("clicking the scrim closes it", !aside.classList.contains("open"));
toggle.click();
document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape" }));
check("Escape closes it", !aside.classList.contains("open"));
toggle.click();
// re-query: render() rebuilt the TOC after the language switches, so the
// links captured at the start of this file are now detached from the DOM
const freshLink = document.querySelector("#toc a");
check("TOC link is attached to the live DOM",
  Boolean(freshLink) && tocEl.contains(freshLink));
freshLink.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
check("following a TOC link closes it", !aside.classList.contains("open"));

console.log("\n— token claim stays honest —");
const claim = (doc.textContent.match(/~([\d,]+) tokens/) || [])[1];
check("header states a token count", Boolean(claim), `~${claim} tokens`);
const est = Math.round(src.en.raw.length / 4.0);
check("stated count matches the built estimate within 2%",
  Math.abs(parseInt(claim.replace(/,/g, ""), 10) - est) / est < 0.02,
  `stated ~${claim} vs estimate ${est}`);

console.log("\n— evaluation section —");
const evalRows = doc ? document.querySelectorAll(".evaltable tr.tid, .evaltable td.tid") : [];
const evalBox = document.getElementById("evalbox");
check("eval section rendered", Boolean(evalBox));
check("one table row per task",
  document.querySelectorAll(".evaltable td.tid").length === 28,
  `${document.querySelectorAll(".evaltable td.tid").length} rows`);
check("one category header per category",
  document.querySelectorAll(".evaltable tr.catrow").length === 15,
  `${document.querySelectorAll(".evaltable tr.catrow").length} headers`);
check("stated task count matches tasks.json",
  evalBox.textContent.includes("28 zada\u0144"),
  '"28 zada\u0144"');
check("stated check count matches tasks.json",
  evalBox.textContent.includes("65 deterministycznych"),
  '"65 deterministycznych"');
const evalCopy = evalBox.querySelector("[data-copy-code]");
check("eval code block has a copy button", Boolean(evalCopy));
evalCopy.click();
await settle(20);
check("eval copy button works", (clipboardLog.at(-1) || "").includes("harness.py"),
  JSON.stringify((clipboardLog.at(-1) || "").slice(0, 40)));
check("eval copy button is not double-wired", evalCopy.dataset.wired === "1");
document.querySelector('.seg button[data-lang="pl"]').click();
await settle(40);
document.querySelector('.seg button[data-lang="en"]').click();
await settle(40);
const evalCopy2 = document.getElementById("evalbox").querySelector("[data-copy-code]");
clipboardLog.length = 0;
evalCopy2.click();
evalCopy2.click();
await settle(20);
check("repeated renders do not stack listeners", clipboardLog.length === 2,
  `${clipboardLog.length} writes for 2 clicks`);

console.log("\n— final —");
check("no uncaught JS errors after full interaction", errors.length === 0,
  errors.join("; ") || "clean");
check("no unmapped-section warnings at all", warnings.length === 0,
  warnings.join(" | ") || "none");

console.log(
  failures === 0
    ? `\nALL CHECKS PASSED — ${clipboardLog.length} clipboard writes, ${downloads.length} downloads\n`
    : `\n${failures} CHECK(S) FAILED\n`,
);
process.exit(failures === 0 ? 0 : 1);
