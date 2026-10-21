export interface MetaLoginResponse {
  authResponse?: {
    code?: string;
    accessToken?: string;
  } | null;
}

export interface MetaLoginOptions {
  config_id: string;
  response_type?: "code";
  override_default_response_type?: true;
  extras?: {
    setup: Record<string, never>;
  };
}

export interface MetaSdk {
  init(options: {
    appId: string;
    autoLogAppEvents: boolean;
    xfbml: boolean;
    version: string;
  }): void;
  login(callback: (response: MetaLoginResponse) => void, options: MetaLoginOptions): void;
}

declare global {
  interface Window {
    FB?: MetaSdk;
    fbAsyncInit?: () => void;
  }
}

let sdkLoad: Promise<MetaSdk> | undefined;
let initializedAppId: string | undefined;

export function loadMetaSdk(appId: string): Promise<MetaSdk> {
  if (!appId) return Promise.reject(new Error("Meta app ID is not configured."));
  if (window.FB && initializedAppId === appId) return Promise.resolve(window.FB);

  if (!sdkLoad) {
    sdkLoad = new Promise<MetaSdk>((resolve, reject) => {
      let settled = false;
      const finish = (error?: Error) => {
        if (settled) return;
        settled = true;
        if (error) {
          reject(error);
          return;
        }
        if (!window.FB) {
          reject(new Error("Meta login SDK did not initialize."));
          return;
        }
        window.FB.init({
          appId,
          autoLogAppEvents: true,
          xfbml: false,
          version: "v26.0",
        });
        initializedAppId = appId;
        resolve(window.FB);
      };

      window.fbAsyncInit = () => finish();
      const existing = document.getElementById("joy-meta-sdk") as HTMLScriptElement | null;
      if (existing) {
        if (window.FB) finish();
        else {
          existing.addEventListener("load", () => finish(), { once: true });
          existing.addEventListener("error", () => finish(new Error("Could not load Meta login SDK.")), { once: true });
        }
        return;
      }

      const script = document.createElement("script");
      script.id = "joy-meta-sdk";
      script.src = "https://connect.facebook.net/en_US/sdk.js";
      script.async = true;
      script.defer = true;
      script.crossOrigin = "anonymous";
      script.onload = () => finish();
      script.onerror = () => finish(new Error("Could not load Meta login SDK."));
      document.head.appendChild(script);
    }).finally(() => {
      sdkLoad = undefined;
    });
  }

  return sdkLoad.then((sdk) => {
    if (initializedAppId !== appId) {
      sdk.init({
        appId,
        autoLogAppEvents: true,
        xfbml: false,
        version: "v26.0",
      });
      initializedAppId = appId;
    }
    return sdk;
  });
}
