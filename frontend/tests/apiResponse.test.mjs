import test from "node:test";
import assert from "node:assert/strict";
import {readApiResponse} from "../src/apiResponse.js";

test("plain-text server errors become a useful application error", async () => {
  await assert.rejects(
    readApiResponse(new Response("Internal Server Error", {status: 500})),
    error => error.message === "The ProSight server could not process this request. Please retry or contact support."
      && error.status === 500,
  );
});

test("JSON API details are preserved", async () => {
  await assert.rejects(
    readApiResponse(new Response(JSON.stringify({detail: "Workbook mapping is invalid"}), {
      status: 400,
      headers: {"Content-Type": "application/json"},
    })),
    error => error.message === "Workbook mapping is invalid" && error.status === 400,
  );
});

test("successful JSON responses are returned", async () => {
  const payload = await readApiResponse(new Response(JSON.stringify({ok: true}), {status: 200}));
  assert.deepEqual(payload, {ok: true});
});
