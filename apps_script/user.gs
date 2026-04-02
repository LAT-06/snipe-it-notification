const USERS_API_ENDPOINT = APILib.getEndpointUsers();
const USERS_API_KEY = APILib.getApiKey();
const CREATE_IF_MISSING = true;

function getApiKey_() {
  if (APILib && typeof APILib.getApiKey === "function") return APILib.getApiKey();
  if (APILib && typeof APILib.getMyApiKey === "function") return APILib.getMyApiKey();
  return "";
}

function getEndpointUsers_() {
  if (APILib && typeof APILib.getEndpointUsers === "function") return APILib.getEndpointUsers();
  return PropertiesService.getScriptProperties().getProperty("API_Endpoint_users") || "";
}

const USER_HEADERS = [
  "First Name", "Last Name", "Email", "Username", "Display Name", "Activated",
  "Location", "Address", "City", "State", "Country", "Postal Code", "Website",
  "Phone", "Job Title", "Notes", "Employee Number", "Company", "Manager",
  "Remote", "VIP", "Start Date", "End Date", "Gravatar",
];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Snipe-IT Users")
    .addItem("Sync this sheet to Snipe-IT Users", "syncUsersCurrentSheet")
    .addToUi();
}

function syncUsersCurrentSheet() {
  if (!USERS_API_ENDPOINT) {
    SpreadsheetApp.getUi().alert("Missing endpoint from APILib.getEndpointUsers().");
    return;
  }
  if (!USERS_API_KEY) {
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

  const headerRow = data[0].map(h => String(h).trim());
  const rows = [];

  for (let i = 1; i < data.length; i++) {
    const raw = data[i];
    if (raw.every(cell => cell === "" || cell === null)) continue;

    const rowObj = {};
    USER_HEADERS.forEach(header => {
      const idx = headerRow.indexOf(header);
      if (idx !== -1) {
        const val = raw[idx];
        rowObj[header] = val instanceof Date
          ? Utilities.formatDate(val, Session.getScriptTimeZone(), "yyyy-MM-dd")
          : String(val || "").trim();
      } else {
        rowObj[header] = "";
      }
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
    create_if_missing: CREATE_IF_MISSING,
    rows,
  });

  const options = {
    method: "post",
    contentType: "application/json",
    headers: { "x-api-key": USERS_API_KEY },
    payload,
    muteHttpExceptions: true,
  };

  try {
    const response = UrlFetchApp.fetch(USERS_API_ENDPOINT, options);
    const code = response.getResponseCode();
    const body = JSON.parse(response.getContentText() || "{}");

    if (code === 200) {
      const topSkipped = Array.isArray(body.skipped_details)
        ? body.skipped_details.slice(0, 3).map(item =>
            `- Row ${item.row} | ${item.email || item.username || "N/A"} | ${item.reason}`
          ).join("\n")
        : "";

      const topErrors = Array.isArray(body.errors)
        ? body.errors.slice(0, 3).map(item =>
            `- Row ${item.row} | ${item.email || item.username || "N/A"} | ${item.error}`
          ).join("\n")
        : "";

      SpreadsheetApp.getUi().alert(
        `Users sync finished!\n` +
        `Updated: ${body.updated || 0}\n` +
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
