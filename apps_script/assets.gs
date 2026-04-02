const API_ENDPOINT = APILib.getEndpointAssets();
const API_KEY = APILib.getApiKey();
const SOURCE_SYSTEM = "google_sheets";

// Column headers in the expected Google Sheet order
const HEADERS = [
  "Company", "Name", "Asset Tag", "Serial Number", "Category",
  "Status", "Supplier", "Manufacturer", "Location", "Order Number",
  "Model", "Model Notes", "Model Number", "Asset Notes", "Purchase Date",
  "Purchase Cost", "Checkout Type", "Checked Out To: Username",
  "Checked Out To: First Name", "Checked Out To: Last Name",
  "Checked Out To: Email", "Checkout to Location", "Warranty", "EOL Date",
];

/**
 * Create a custom menu when opening the spreadsheet
 */
function onOpen() {
  addSnipeItMenu_();
}

/**
 * Allows manual menu setup from Apps Script editor without breaking execution.
 */
function setupMenu() {
  addSnipeItMenu_();
}

function addSnipeItMenu_() {
  try {
    SpreadsheetApp.getUi()
      .createMenu("Snipe-IT")
      .addItem("Sync this sheet to Snipe-IT", "syncCurrentSheet")
      .addToUi();
  } catch (e) {
    // No UI context (e.g., manual run from editor): ignore safely.
    Logger.log(`Menu creation skipped: ${e.message}`);
  }
}

/**
 * Main flow: read current sheet and send payload to Lambda
 */
function syncCurrentSheet() {
  if (!API_KEY) {
    SpreadsheetApp.getUi().alert("Missing API key from APILib.getApiKey().");
    return;
  }
  if (!API_ENDPOINT) {
    SpreadsheetApp.getUi().alert("Missing endpoint from APILib.getEndpointAssets().");
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

  // The first row is the sheet header; map headers to column indexes
  const headerRow = data[0].map(h => h.toString().trim());
  const rows = [];

  for (let i = 1; i < data.length; i++) {
    const raw = data[i];

    // Skip completely empty rows
    if (raw.every(cell => cell === "" || cell === null)) continue;

    const rowObj = {};
    HEADERS.forEach(header => {
      const idx = headerRow.indexOf(header);
      if (idx !== -1) {
        const val = raw[idx];
        // Format date cells as YYYY-MM-DD for Snipe-IT
        if (val instanceof Date) {
          rowObj[header] = Utilities.formatDate(val, Session.getScriptTimeZone(), "yyyy-MM-dd");
        } else {
          rowObj[header] = val.toString().trim();
        }
      } else {
        rowObj[header] = "";
      }
    });

    rows.push(rowObj);
  }

  const payload = JSON.stringify({
    source: SOURCE_SYSTEM,
    spreadsheet_id: spreadsheetId,
    sheet_name: sheetName,
    timezone: Session.getScriptTimeZone(),
    imported_at: new Date().toISOString(),
    // Batch ID helps trace each sync run
    batch_id: `${sheetName}-${Date.now()}`,
    rows,
  });

  const options = {
    method: "post",
    contentType: "application/json",
    headers: { "x-api-key": API_KEY },
    payload,
    muteHttpExceptions: true, // do not throw; handle response manually
  };

  try {
    const response = UrlFetchApp.fetch(API_ENDPOINT, options);
    const code = response.getResponseCode();
    const body = JSON.parse(response.getContentText() || "{}");

    if (code === 200) {
      let errorPreview = "";
      if (Array.isArray(body.errors) && body.errors.length > 0) {
        const lines = body.errors.slice(0, 3).map(item =>
          `- Row ${item.row} | Asset Tag: ${item.asset_tag || "N/A"} | ${item.error}`
        );
        errorPreview = `\n\nTop errors:\n${lines.join("\n")}`;
      }

      SpreadsheetApp.getUi().alert(
        `Sync completed successfully!\nImported: ${body.imported} assets | Failed: ${body.failed} assets\n\nSee details in Google Chat.${errorPreview}`
      );
    } else {
      SpreadsheetApp.getUi().alert(`Server error (${code}):\n${response.getContentText()}`);
    }
  } catch (e) {
    SpreadsheetApp.getUi().alert(`Cannot connect to server:\n${e.message}`);
  }
}