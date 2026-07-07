// SIP client for the Zadarma account.
//
// Registers to the SIP server using the credentials from config (settings),
// performing RFC 2617 digest authentication, and periodically re-registers
// before the registration expires.
//
// Run directly:  node sip-client.js   (or: npm run sip)
// Or import:     import { registerSip } from "./sip-client.js";

import sip from "sip";
import digest from "sip/digest.js";
import os from "node:os";

import { config } from "./config.js";

function rstring() {
  return Math.floor(Math.random() * 1e6).toString();
}

// Best-effort local IPv4 address for the Contact header.
function localAddress() {
  const ifaces = os.networkInterfaces();
  for (const name of Object.keys(ifaces)) {
    for (const iface of ifaces[name] || []) {
      if (iface.family === "IPv4" && !iface.internal) return iface.address;
    }
  }
  return "127.0.0.1";
}

/**
 * Register a SIP account and keep the registration fresh.
 * @param {object} sipCfg - config.sip
 * @param {object} [opts]
 * @param {(status: {registered: boolean, code?: number, reason?: string}) => void} [opts.onStatus]
 * @returns {{ stop: () => void }}
 */
export function registerSip(sipCfg, opts = {}) {
  const { domain, username, password, expires, port } = sipCfg;
  const onStatus = opts.onStatus || (() => {});

  if (!username || !password) {
    throw new Error(
      "SIP username/password missing. Set SIP_USERNAME and SIP_PASSWORD in .env"
    );
  }

  const contactHost = localAddress();
  const callId = rstring();
  const fromTag = rstring();
  let cseq = 1;
  let renewTimer = null;
  let stopped = false;

  // Start the SIP stack. Reply politely to anything the server sends us.
  sip.start({ port }, (rq) => {
    sip.send(sip.makeResponse(rq, 405, "Method Not Allowed"));
  });

  function buildRegister() {
    return {
      method: "REGISTER",
      uri: `sip:${domain}`,
      headers: {
        to: { uri: `sip:${username}@${domain}` },
        from: { uri: `sip:${username}@${domain}`, params: { tag: fromTag } },
        "call-id": callId,
        cseq: { method: "REGISTER", seq: cseq },
        contact: [{ uri: `sip:${username}@${contactHost}:${port}` }],
        expires,
      },
    };
  }

  function scheduleRenew() {
    if (stopped) return;
    // Re-register at ~80% of the expiry window.
    const ms = Math.max(30, Math.floor(expires * 0.8)) * 1000;
    renewTimer = setTimeout(() => {
      cseq += 1;
      sendRegister();
    }, ms);
    if (renewTimer.unref) renewTimer.unref();
  }

  function handleFinal(rs) {
    if (rs.status === 200) {
      console.log(`SIP registered as ${username}@${domain} (expires ${expires}s)`);
      onStatus({ registered: true, code: 200, reason: rs.reason });
      scheduleRenew();
    } else {
      console.error(`SIP registration failed: ${rs.status} ${rs.reason}`);
      onStatus({ registered: false, code: rs.status, reason: rs.reason });
    }
  }

  function sendRegister() {
    const rq = buildRegister();
    sip.send(rq, (rs) => {
      if (rs.status === 401 || rs.status === 407) {
        // Challenge received — sign a fresh request with a new CSeq and resend.
        cseq += 1;
        const authReq = buildRegister();
        const session = {};
        digest.signRequest(session, authReq, rs, { user: username, password });
        sip.send(authReq, handleFinal);
      } else {
        handleFinal(rs);
      }
    });
  }

  console.log(`Connecting SIP ${username}@${domain} (local ${contactHost}:${port})...`);
  sendRegister();

  return {
    stop() {
      stopped = true;
      if (renewTimer) clearTimeout(renewTimer);
      // Best-effort de-registration (expires 0).
      cseq += 1;
      const rq = buildRegister();
      rq.headers.expires = 0;
      rq.headers.contact = [{ uri: `sip:${username}@${contactHost}:${port}`, params: { expires: 0 } }];
      try {
        sip.send(rq, () => sip.stop());
      } catch {
        sip.stop();
      }
    },
  };
}

// When run directly, register using the settings from config.
const isMain =
  process.argv[1] && import.meta.url === `file://${process.argv[1]}`;

if (isMain) {
  const handle = registerSip(config.sip);
  process.on("SIGINT", () => {
    console.log("\nStopping SIP client...");
    handle.stop();
    setTimeout(() => process.exit(0), 500);
  });
}
