const CATEGORIES_API_ENDPOINT = APILib.getEndpointCategories();
const CATEGORIES_API_KEY = APILib.getApiKey();

function getApiKey_() {
  if (APILib && typeof APILib.getApiKey === "function") return APILib.getApiKey();
  if (APILib && typeof APILib.getMyApiKey === "function") return APILib.getMyApiKey();
  return "";
}

function getEndpointCategories_() {
  if (APILib && typeof APILib.getEndpointCategories === "function") return APILib.getEndpointCategories();
  return PropertiesService.getScriptProperties().getProperty("API_Endpoint_categories") || "";
}

const CATEGORY_HEADERS = [
  "name",
  "category type",
  "notes",
  "require acceptance",
  "checkin email",
  "use default eula",
  "eula text",
];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Snipe-IT Categories")
    .addItem("Sync this sheet to Snipe-IT Categories", "syncCategoriesCurrentSheet")
    .addToUi();
}

function syncCategoriesCurrentSheet() {
  if (!CATEGORIES_API_ENDPOINT) {
    SpreadsheetApp.getUi().alert("Missing endpoint from APILib.getEndpointCategories().");
    return;
  }
  if (!CATEGORIES_API_KEY) {
    SpreadsheetApp.getUi().alert("Missing API key from APILib (getApiKey/getMyApiKey).");
    return;
  }

  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const sheetName = sheet.getName();
  const spreadsheetId = SpreadsheetApp.getActiveSpreadsheet().getId();
  const data = sheet.getDataRange().getValues();

  if (data.length < 2) {
    SpreadsheetApp.getUi().alert("This sheet has no data (header only or empty).");
    return;
  }

  const headerRow = data[0].map(h => String(h).trim().toLowerCase());
  const rows = [];

  for (let i = 1; i < data.length; i++) {
    const raw = data[i];
    if (raw.every(cell => cell === "" || cell === null)) continue;

    const rowObj = {};
    CATEGORY_HEADERS.forEach(header => {
      const idx = headerRow.indexOf(header);
      const val = idx >= 0 ? raw[idx] : "";
      rowObj[header] = val instanceof Date
        ? Utilities.formatDate(val, Session.getScriptTimeZone(), "yyyy-MM-dd")
        : String(val || "").trim();
    });
    rows.push(rowObj);
  }

  const payload = JSON.stringify({
    source: "google_sheets",
    spreadsheet_id: spreadsheetId,
    sheet_name: sheetName,
    timezone: Session.getScriptTimeZone(),
    imported_at: new Date().toISOString(),
    batch_id: `${sheetName}-${Date.now()}`,
    rows,
  });

  const options = {
    method: "post",
    contentType: "application/json",
    headers: { "x-api-key": CATEGORIES_API_KEY },
    payload,
    muteHttpExceptions: true,
  };

  try {
    const response = UrlFetchApp.fetch(CATEGORIES_API_ENDPOINT, options);
    const code = response.getResponseCode();
    const body = JSON.parse(response.getContentText() || "{}");

    if (code === 200) {
      const topSkipped = Array.isArray(body.skipped_details)
        ? body.skipped_details.slice(0, 3).map(item =>
            `- Row ${item.row} | ${item.name || "N/A"} | ${item.reason}`
          ).join("\n")
        : "";

      const topErrors = Array.isArray(body.errors)
        ? body.errors.slice(0, 3).map(item =>
            `- Row ${item.row} | ${item.name || "N/A"} | ${item.error}`
          ).join("\n")
        : "";

      SpreadsheetApp.getUi().alert(
        `Categories sync finished!\n` +
        `Created: ${body.created || 0}\n` +
        `Skipped: ${body.skipped || 0}\n` +
        `Failed: ${body.failed || 0}` +
        (topSkipped ? `\n\nTop skipped:\n${topSkipped}` : "") +
        (topErrors ? `\n\nTop errors:\n${topErrors}` : "")
      );
    } else {
      SpreadsheetApp.getUi().alert(`Server error (${code}):\n${response.getContentText()}`);
    }
  } catch (e) {
    SpreadsheetApp.getUi().alert(`Cannot connect to server:\n${e.message}`);
  }
}
