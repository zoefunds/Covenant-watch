"use client";

export type Eip1193Provider = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
  on?: (event: string, cb: (...args: any[]) => void) => void;
  removeListener?: (event: string, cb: (...args: any[]) => void) => void;
};

export type WalletProvider = {
  info: { uuid: string; name: string; icon: string; rdns: string };
  provider: Eip1193Provider;
};

const providers = new Map<string, WalletProvider>();
let selected: WalletProvider | null = null;
let initialized = false;
let picker: ((wallets: WalletProvider[]) => Promise<WalletProvider>) | null = null;

function legacyProvider(): WalletProvider | null {
  if (typeof window === "undefined") return null;
  const provider = (window as typeof window & { ethereum?: Eip1193Provider }).ethereum;
  return provider ? { info: { uuid: "legacy", name: "Browser wallet", icon: "", rdns: "legacy.injected" }, provider } : null;
}

function initializeDiscovery() {
  if (initialized || typeof window === "undefined") return;
  initialized = true;
  window.addEventListener("eip6963:announceProvider", ((event: CustomEvent<WalletProvider>) => {
    const detail = event.detail;
    if (detail?.info?.uuid && detail.provider) providers.set(detail.info.uuid, detail);
  }) as EventListener);
  window.dispatchEvent(new Event("eip6963:requestProvider"));
}

export async function discoverWalletProviders(waitMs = 200): Promise<WalletProvider[]> {
  initializeDiscovery();
  if (providers.size === 0 && waitMs > 0) await new Promise((resolve) => window.setTimeout(resolve, waitMs));
  const discovered = [...providers.values()];
  if (discovered.length > 0) return discovered;
  const legacy = legacyProvider();
  return legacy ? [legacy] : [];
}

export function registerWalletPicker(handler: ((wallets: WalletProvider[]) => Promise<WalletProvider>) | null) {
  picker = handler;
}

export async function requestWalletProvider(): Promise<Eip1193Provider> {
  if (selected) return selected.provider;
  const wallets = await discoverWalletProviders();
  if (wallets.length === 0) throw new Error("No browser wallet found. Install MetaMask or another EIP-1193 wallet and refresh.");
  if (wallets.length === 1) selected = wallets[0];
  else {
    if (!picker) throw new Error("Wallet chooser is not ready. Please try again.");
    selected = await picker(wallets);
  }
  return selected.provider;
}

export function getSelectedWalletProvider(): Eip1193Provider | null {
  return selected?.provider || legacyProvider()?.provider || null;
}

export function clearSelectedWalletProvider() {
  selected = null;
}
