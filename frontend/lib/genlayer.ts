import { createClient } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
import {
  TransactionStatus,
  ExecutionResult,
} from "genlayer-js/types";

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

  /*
   * IMPORTANT:
   *
   * We intentionally use the direct GenLayer Chain RPC
   * here because this is the RPC that successfully handled
   * MetaMask eth_sendRawTransaction in our testing.
   */
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

/*
 * Reads use the normal GenLayer Bradbury client.
 *
 * This is intentional.
 *
 * GenLayer RPC provides the GenLayer-specific methods
 * required for intelligent-contract reads and transaction
 * state.
 */
export function readClient() {
  return createClient({
    chain: testnetBradbury,
  });
}

/* =========================================================
   WALLET / NETWORK MANAGEMENT
   ========================================================= */

/**
 * Make sure MetaMask is connected to GenLayer Bradbury
 * using the direct GenLayer Chain RPC.
 */
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

  /*
   * Already on Bradbury.
   */
  if (
    String(currentChainId).toLowerCase() ===
    BRADBURY_CHAIN_ID
  ) {
    return;
  }

  /*
   * Try switching to Bradbury if it already exists
   * in MetaMask.
   */
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

    /*
     * MetaMask error 4902 means the chain does not
     * exist in the wallet.
     */
    if (switchError?.code !== 4902) {
      throw switchError;
    }
  }

  /*
   * Add Bradbury using the DIRECT Chain RPC.
   */
  await provider.request({
    method: "wallet_addEthereumChain",
    params: [
      BRADBURY_NETWORK,
    ],
  });

  /*
   * Switch again after adding.
   */
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

  /*
   * Configure/switch MetaMask BEFORE requesting
   * the wallet account.
   */
  await ensureBradburyNetwork(provider);

  /*
   * Request wallet permission.
   */
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

  /*
   * Verify the final network.
   */
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

  console.log(
    "Network: GenLayer Testnet Bradbury"
  );

  console.log(
    "RPC: https://rpc.testnet-chain.genlayer.com"
  );

  return {
    address,
    provider,
  };
}

/* =========================================================
   WRITE CLIENT
   ========================================================= */

/**
 * Create the wallet-backed GenLayerJS client.
 *
 * IMPORTANT:
 *
 * We DO NOT call:
 *
 *   client.connect("testnetBradbury")
 *
 * here.
 *
 * MetaMask has already been configured manually through
 * ensureBradburyNetwork().
 */
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
) {
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
   WAIT FOR TRANSACTION
   ========================================================= */

async function wait(
  client: any,
  hash: any,
  retries: number
) {
  console.log(
    "Waiting for transaction:",
    hash
  );

  const receipt =
    await client.waitForTransactionReceipt({
      hash,

      status:
        TransactionStatus.FINALIZED,

      interval: 5000,

      retries,
    });

  console.log(
    "Transaction finalized:",
    receipt
  );

  /*
   * Check contract execution result.
   */
  if (
    receipt.txExecutionResultName &&
    receipt.txExecutionResultName !==
      ExecutionResult.FINISHED_WITH_RETURN
  ) {
    throw new Error(
      `Transaction finalized but execution failed: ${String(
        receipt.txExecutionResultName
      )}`
    );
  }

  return receipt;
}

/* =========================================================
   CREATE POLICY
   ========================================================= */

export async function createPolicy(
  address: `0x${string}`,
  provider: EthereumProvider,

  data: {
    flightNumber: string;
    departureDate: string;
    sourceUrl: string;
    payoutAmount: string;
  },

  onHash: (h: string) => void
) {
  /*
   * Verify the wallet network before writing.
   */
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

  /*
   * Send transaction.
   *
   * MetaMask handles signing.
   */
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

  console.log(
    "Policy transaction submitted:",
    hash
  );

  onHash(
    String(hash)
  );

  return wait(
    client,
    hash,
    120
  );
}

/* =========================================================
   EVALUATE POLICY
   ========================================================= */

export async function evaluatePolicy(
  address: `0x${string}`,
  provider: EthereumProvider,
  id: string,
  onHash: (h: string) => void
) {
  /*
   * Verify the wallet network before writing.
   */
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

  /*
   * This transaction triggers the actual
   * GenLayer Intelligent Contract evaluation.
   */
  const hash =
    await client.writeContract({
      address:
        contractAddress(),

      functionName:
        "evaluate_policy",

      args: [id],

      value: BigInt(0),
    });

  console.log(
    "Evaluation transaction submitted:",
    hash
  );

  onHash(
    String(hash)
  );

  /*
   * Evaluation takes longer because validators
   * need to reach consensus.
   */
  return wait(
    client,
    hash,
    180
  );
}