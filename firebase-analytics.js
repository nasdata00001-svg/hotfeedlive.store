// HOTFEED LIVE - Firebase Analytics Integration (ES Module CDN)
import {
  getApp,
  getApps,
  initializeApp,
} from "https://www.gstatic.com/firebasejs/13.4.0/firebase-app.js";
import {
  getAnalytics,
  isSupported,
  logEvent,
} from "https://www.gstatic.com/firebasejs/13.4.0/firebase-analytics.js";

const firebaseConfig = {
  apiKey: "AIzaSyDQrZAdT2mXzQl2tDxzYKLS2tF5CXxC4Hs",
  authDomain: "hotfeedlive.firebaseapp.com",
  projectId: "hotfeedlive",
  storageBucket: "hotfeedlive.firebasestorage.app",
  messagingSenderId: "1033441018228",
  appId: "1:1033441018228:web:2040e08d2c910df329ac21",
  measurementId: "G-WB0T560XLP",
};

window.firebaseAnalyticsState = {
  ready: false,
  supported: null,
  measurementId: firebaseConfig.measurementId,
};

async function initFirebaseAnalytics() {
  try {
    const supported = await isSupported().catch(() => false);
    window.firebaseAnalyticsState.supported = supported;

    if (!supported) {
      if (Array.isArray(window.__pendingAnalyticsEvents)) {
        window.__pendingAnalyticsEvents.length = 0;
      }
      return;
    }

    const app = getApps().length ? getApp() : initializeApp(firebaseConfig);
    const analytics = getAnalytics(app);

    window.firebaseApp = app;
    window.firebaseAnalytics = analytics;
    window.firebaseAnalyticsState.ready = true;

    window.trackAnalyticsEvent = (eventName, params = {}) => {
      try {
        logEvent(analytics, eventName, params);
      } catch (err) {
        console.debug("Firebase Analytics log skipped:", err);
      }
    };

    if (Array.isArray(window.__pendingAnalyticsEvents) && window.__pendingAnalyticsEvents.length > 0) {
      const queued = window.__pendingAnalyticsEvents.splice(0);
      queued.forEach((evt) => {
        if (evt && evt.name) {
          window.trackAnalyticsEvent(evt.name, evt.params || {});
        }
      });
    }
  } catch (err) {
    console.warn("Firebase Analytics initialization notice:", err);
  }
}

initFirebaseAnalytics();
