/** Parse one API response without masking plain-text or malformed server errors. */
export async function readApiResponse(response, fallbackMessage = "The request could not be completed.") {
  const raw = await response.text();
  let payload = null;
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = null;
    }
  }
  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : "";
    const message = detail || (response.status >= 500
      ? "The ProSight server could not process this request. Please retry or contact support."
      : fallbackMessage);
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  if (payload === null) {
    throw new Error("The ProSight server returned an invalid response. Please retry.");
  }
  return payload;
}
