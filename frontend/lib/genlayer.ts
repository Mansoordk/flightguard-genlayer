import { createClient } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
import { ExecutionResult } from "genlayer-js/types";

/* =========================================================
   TYPES
   ========================================================= */

export type EthereumProvider = {
  request: (args: {
    method: string;
    params?: unknown[];
  }) => Promise<unknown>;
};

export type Policy = {
  policy_id: string;
  owner: string;
  flight_number: string;
  departure_date: string;
  source_url: string;
  payout_amount: string;
  status: string;
  decision: number;
  summary: string;
  evidence: string;
};

/* =========================================================
   TRANSACTION TYPES
   ========================================================= */

export type GenLayerStatusName =
  | "UNINITIALIZED"
  | "PENDING"
  | "PROPOSING"
  | "COMMITTING"
  | "REVEALING"
  | "ACCEPTED"
  | "UNDETERMINED"
  | "FINALIZED"
  | "CANCELED"
  | "APPEAL_REVEALING"
  | "APPEAL_COMMITTING"
  | "VALIDATORS_TIMEOUT"
  | "LEADER_TIMEOUT"
  | "LEADER_REVEALING"
  | "UNKNOWN";

export type GenLayerTransactionSnapshot = {
  hash: string;
  statusName: GenLayerStatusName;
  statusCode?: number;
  txExecutionResultName?: string;
  lifecycle?: string;
  queuePosition?: number | null;
  projectedStatus?: string | null;
  resolutionAction?: string | null;
  resolutionSource?: string | null;
  updatedAt: number;
};

/* =========================================================
   CONFIGURATION
   ========================================================= */

const CONTRACT =
  process.env.NEXT_PUBLIC_GENLAYER_CONTRACT_ADDRESS || "";

const BRADBURY_CHAIN_ID = "0x107d";

const BRADBURY_NETWORK = {
  chainId: BRADBURY_CHAIN_ID,
  chainName: "GenLayer Testnet Bradbury",

  nativeCurrency: {
    name: "GEN",
    symbol: "GEN",
    decimals: 18,
  },

  rpcUrls: [
    "https://rpc.testnet-chain.genlayer.com",
  ],

  blockExplorerUrls: [
    "https://explorer-bradbury.genlayer.com",
  ],
};

/* =========================================================
   CONTRACT ADDRESS
   ========================================================= */

export function contractAddress(): `0x${string}` {
  if (!CONTRACT) {
    throw new Error(
      "Missing NEXT_PUBLIC_GENLAYER_CONTRACT_ADDRESS in .env.local"
    );
  }

  return CONTRACT as `0x${string}`;
}

/* =========================================================
   READ CLIENT
   ========================================================= */

export function readClient() {
  return createClient({
    chain: testnetBradbury,
  });
}

/* =========================================================
   WALLET / NETWORK MANAGEMENT
   ========================================================= */

async function ensureBradburyNetwork(
  provider: EthereumProvider
) {
  const currentChainId =
    await provider.request({
      method: "eth_chainId",
    });

  console.log(
    "Current MetaMask chain:",
    currentChainId
  );

  if (
    String(currentChainId).toLowerCase() ===
    BRADBURY_CHAIN_ID
  ) {
    return;
  }

  try {
    await provider.request({
      method: "wallet_switchEthereumChain",
      params: [
        {
          chainId: BRADBURY_CHAIN_ID,
        },
      ],
    });

    return;
  } catch (switchError: any) {
    console.log(
      "Bradbury is not configured in MetaMask.",
      switchError
    );

    if (switchError?.code !== 4902) {
      throw switchError;
    }
  }

  await provider.request({
    method: "wallet_addEthereumChain",
    params: [
      BRADBURY_NETWORK,
    ],
  });

  await provider.request({
    method: "wallet_switchEthereumChain",
    params: [
      {
        chainId: BRADBURY_CHAIN_ID,
      },
    ],
  });
}

/* =========================================================
   CONNECT WALLET
   ========================================================= */

export async function connectWallet() {
  if (
    typeof window === "undefined" ||
    !(window as any).ethereum
  ) {
    throw new Error(
      "No browser wallet found. Please install MetaMask."
    );
  }

  const provider =
    (window as any).ethereum as EthereumProvider;

  await ensureBradburyNetwork(provider);

  const accounts =
    (await provider.request({
      method: "eth_requestAccounts",
    })) as string[];

  if (!accounts?.[0]) {
    throw new Error(
      "No wallet account returned."
    );
  }

  const address =
    accounts[0] as `0x${string}`;

  const finalChainId =
    await provider.request({
      method: "eth_chainId",
    });

  if (
    String(finalChainId).toLowerCase() !==
    BRADBURY_CHAIN_ID
  ) {
    throw new Error(
      `Wrong network. Please switch to GenLayer Testnet Bradbury. Current chain: ${finalChainId}`
    );
  }

  console.log(
    "FlightGuard wallet connected:",
    address
  );

  return {
    address,
    provider,
  };
}

/* =========================================================
   WRITE CLIENT
   ========================================================= */

function writeClient(
  address: `0x${string}`,
  provider: EthereumProvider
) {
  return createClient({
    chain: testnetBradbury,
    account: address,
    provider,
  });
}

/* =========================================================
   READ POLICIES
   ========================================================= */

export async function readPolicies(
  address: string
): Promise<Policy[]> {
  const client = readClient();

  const result =
    await client.readContract({
      address: contractAddress(),

      functionName:
        "get_policies_for_user",

      args: [address],
    });

  return result as Policy[];
}

/* =========================================================
   NORMALIZE GENLAYER STATUS
   ========================================================= */

function normalizeStatus(
  value: unknown
): GenLayerStatusName {
  const status =
    String(value || "")
      .trim()
      .toUpperCase()
      .replace(/[\s-]+/g, "_");

  switch (status) {
    case "UNINITIALIZED":
      return "UNINITIALIZED";

    case "PENDING":
      return "PENDING";

    case "PROPOSING":
      return "PROPOSING";

    case "COMMITTING":
      return "COMMITTING";

    case "REVEALING":
      return "REVEALING";

    case "ACCEPTED":
      return "ACCEPTED";

    case "UNDETERMINED":
      return "UNDETERMINED";

    case "FINALIZED":
      return "FINALIZED";

    case "CANCELED":
    case "CANCELLED":
      return "CANCELED";

    case "APPEAL_REVEALING":
      return "APPEAL_REVEALING";

    case "APPEAL_COMMITTING":
      return "APPEAL_COMMITTING";

    case "VALIDATORS_TIMEOUT":
      return "VALIDATORS_TIMEOUT";

    case "LEADER_TIMEOUT":
      return "LEADER_TIMEOUT";

    case "LEADER_REVEALING":
      return "LEADER_REVEALING";

    default:
      return "UNKNOWN";
  }
}

/* =========================================================
   NUMBER HELPER
   ========================================================= */

function normalizeNumber(
  value: unknown
): number | undefined {
  if (
    value === null ||
    value === undefined
  ) {
    return undefined;
  }

  const numberValue =
    Number(value);

  return Number.isFinite(numberValue)
    ? numberValue
    : undefined;
}

/* =========================================================
   GET TRANSACTION STATUS
   ========================================================= */

/**
 * Reads the persisted GenLayer transaction state.
 *
 * IMPORTANT:
 *
 * This does NOT invent a timeout or assume that a transaction
 * failed just because some amount of time has passed.
 *
 * The GenLayer transaction itself remains the source of truth.
 */
export async function getTransactionSnapshot(
  hash: string
): Promise<GenLayerTransactionSnapshot> {
  if (!hash) {
    throw new Error(
      "Transaction hash is missing."
    );
  }

  const client: any =
    readClient();

  if (
    typeof client.getTransaction !==
    "function"
  ) {
    throw new Error(
      "This genlayer-js version does not expose getTransaction(). Please update genlayer-js."
    );
  }

  const transaction =
    await client.getTransaction({
      hash,
    });

  const statusName =
    normalizeStatus(
      transaction?.statusName ??
      transaction?.status
    );

  let projectedStatus:
    string | null = null;

  let resolutionAction:
    string | null = null;

  let resolutionSource:
    string | null = null;

  /*
   * Newer GenLayerJS versions expose the
   * advanced lifecycle API.
   *
   * This is optional so older compatible
   * SDK versions do not break the app.
   */
  try {
    if (
      client.advanced &&
      typeof client.advanced
        .getTransactionLifecycle ===
        "function"
    ) {
      const lifecycle =
        await client.advanced
          .getTransactionLifecycle({
            hash,
          });

      projectedStatus =
        lifecycle?.projectedStatus ??
        null;

      resolutionAction =
        lifecycle?.resolutionAction ??
        null;

      resolutionSource =
        lifecycle?.resolutionSource ??
        null;
    }
  } catch (lifecycleError) {
    console.warn(
      "Lifecycle projection unavailable:",
      lifecycleError
    );
  }

  return {
    hash,

    statusName,

    statusCode:
      normalizeNumber(
        transaction?.status
      ),

    txExecutionResultName:
      transaction?.txExecutionResultName ??
      undefined,

    lifecycle:
      transaction?.lifecycle ??
      undefined,

    queuePosition:
      transaction?.queuePosition ===
      undefined
        ? null
        : normalizeNumber(
            transaction.queuePosition
          ) ?? null,

    projectedStatus,

    resolutionAction,

    resolutionSource,

    updatedAt: Date.now(),
  };
}

/* =========================================================
   WAIT / POLL TRANSACTION
   ========================================================= */

/**
 * Polls a GenLayer transaction until FINALIZED.
 *
 * Unlike the previous implementation, this does not use
 * a short fixed retry window such as 10 or 15 minutes.
 *
 * The UI can remain open or refresh the page and resume
 * monitoring the same transaction hash.
 */
export async function monitorTransaction(
  hash: string,
  onUpdate?: (
    snapshot: GenLayerTransactionSnapshot
  ) => void,
  options?: {
    interval?: number;
    maxAttempts?: number;
  }
): Promise<GenLayerTransactionSnapshot> {
  const interval =
    options?.interval ?? 5000;

  /*
   * 12 hours at 5 seconds.
   *
   * This is only a browser monitoring safety limit.
   * It is NOT treated as an on-chain transaction failure.
   *
   * If the page is refreshed after this point, the
   * persisted hash can be monitored again.
   */
  const maxAttempts =
    options?.maxAttempts ??
    Math.floor(
      (12 * 60 * 60 * 1000) /
        interval
    );

  let attempts = 0;

  let lastError:
    unknown = null;

  while (
    attempts < maxAttempts
  ) {
    attempts++;

    try {
      const snapshot =
        await getTransactionSnapshot(
          hash
        );

      lastError = null;

      onUpdate?.(
        snapshot
      );

      /*
       * Finalized is the terminal successful
       * consensus lifecycle state.
       */
      if (
        snapshot.statusName ===
        "FINALIZED"
      ) {
        return snapshot;
      }

      /*
       * Canceled is terminal.
       */
      if (
        snapshot.statusName ===
        "CANCELED"
      ) {
        return snapshot;
      }
    } catch (error) {
      lastError = error;

      console.warn(
        "Transaction status polling failed:",
        error
      );
    }

    await new Promise<void>(
      (resolve) =>
        setTimeout(
          resolve,
          interval
        )
    );
  }

  /*
   * Do NOT say that the transaction failed.
   *
   * The hash already exists and the chain
   * remains the authority.
   */
  if (lastError) {
    throw new Error(
      `Transaction monitoring is temporarily unavailable. The transaction was already submitted and can be resumed using hash ${hash}.`
    );
  }

  throw new Error(
    `Transaction monitoring paused after a long wait. The transaction was already submitted and can be resumed using hash ${hash}.`
  );
}

/* =========================================================
   EXECUTION SUCCESS CHECK
   ========================================================= */

export function isSuccessfulExecution(
  snapshot: GenLayerTransactionSnapshot
): boolean {
  return (
    snapshot.txExecutionResultName ===
    ExecutionResult.FINISHED_WITH_RETURN
  );
}

/* =========================================================
   CREATE POLICY
   ========================================================= */

/**
 * IMPORTANT:
 *
 * This function ONLY submits the transaction.
 *
 * Once a hash exists, ownership of the transaction
 * moves to the persistent frontend tracker.
 *
 * This prevents the wallet submission from being
 * coupled to a fragile frontend timeout.
 */
export async function createPolicy(
  address: `0x${string}`,
  provider: EthereumProvider,

  data: {
    flightNumber: string;
    departureDate: string;
    sourceUrl: string;
    payoutAmount: string;
  },

  onHash: (
    hash: string
  ) => void
) {
  const chainId =
    await provider.request({
      method: "eth_chainId",
    });

  if (
    String(chainId).toLowerCase() !==
    BRADBURY_CHAIN_ID
  ) {
    throw new Error(
      "MetaMask is not connected to GenLayer Testnet Bradbury."
    );
  }

  const client =
    writeClient(
      address,
      provider
    );

  console.log(
    "Creating FlightGuard policy..."
  );

  console.log(
    "Contract:",
    contractAddress()
  );

  console.log(
    "Wallet:",
    address
  );

  console.log(
    "Flight:",
    data.flightNumber
  );

  const hash =
    await client.writeContract({
      address:
        contractAddress(),

      functionName:
        "create_policy",

      args: [
        data.flightNumber,
        data.departureDate,
        data.sourceUrl,
        data.payoutAmount,
      ],

      value: BigInt(0),
    });

  const txHash =
    String(hash);

  console.log(
    "Policy transaction submitted:",
    txHash
  );

  /*
   * IMPORTANT:
   *
   * Call onHash immediately.
   *
   * The page will persist this hash before
   * starting the long-running tracker.
   */
  onHash(txHash);

  return txHash;
}

/* =========================================================
   EVALUATE POLICY
   ========================================================= */

/**
 * Submits an evaluate_policy transaction.
 *
 * The transaction is NOT waited on here.
 *
 * The persistent frontend tracker owns monitoring.
 */
export async function evaluatePolicy(
  address: `0x${string}`,
  provider: EthereumProvider,
  id: string,

  onHash: (
    hash: string
  ) => void
) {
  const chainId =
    await provider.request({
      method: "eth_chainId",
    });

  if (
    String(chainId).toLowerCase() !==
    BRADBURY_CHAIN_ID
  ) {
    throw new Error(
      "MetaMask is not connected to GenLayer Testnet Bradbury."
    );
  }

  const client =
    writeClient(
      address,
      provider
    );

  console.log(
    "Evaluating FlightGuard policy..."
  );

  console.log(
    "Contract:",
    contractAddress()
  );

  console.log(
    "Policy ID:",
    id
  );

  const hash =
    await client.writeContract({
      address:
        contractAddress(),

      functionName:
        "evaluate_policy",

      args: [id],

      value: BigInt(0),
    });

  const txHash =
    String(hash);

  console.log(
    "Evaluation transaction submitted:",
    txHash
  );

  /*
   * Persist immediately in the frontend.
   */
  onHash(txHash);

  return txHash;
}