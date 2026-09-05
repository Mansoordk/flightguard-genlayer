"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  connectWallet,
  createPolicy,
  evaluatePolicy,
  getTransactionSnapshot,
  isSuccessfulExecution,
  readPolicies,
  type EthereumProvider,
  type GenLayerStatusName,
  type GenLayerTransactionSnapshot,
  type Policy,
} from "../lib/genlayer";

/* =========================================================
   HELPERS
   ========================================================= */

const short = (
  address: string
) =>
  `${address.slice(0, 6)}...${address.slice(-4)}`;

const label = (
  decision: number
) =>
  decision === 1
    ? "QUALIFIED"
    : decision === 0
      ? "NOT QUALIFIED"
      : "UNDETERMINED";

/* =========================================================
   TRANSACTION STORAGE
   ========================================================= */

const STORAGE_KEY =
  "flightguard:pending-transactions:v1";

type TransactionKind =
  | "CREATE_POLICY"
  | "EVALUATE_POLICY";

type TrackedTransaction = {
  id: string;
  hash: string;
  kind: TransactionKind;

  title: string;

  policyId?: string;

  createdAt: number;
  updatedAt: number;

  statusName: GenLayerStatusName;

  statusCode?: number;

  txExecutionResultName?: string;

  queuePosition?: number | null;

  lifecycle?: string;

  projectedStatus?: string | null;

  resolutionAction?: string | null;

  resolutionSource?: string | null;

  state:
    | "TRACKING"
    | "SUCCESS"
    | "FAILED"
    | "PAUSED";

  error?: string;
};

/* =========================================================
   LOCAL STORAGE
   ========================================================= */

function loadTransactions(): TrackedTransaction[] {
  if (
    typeof window ===
    "undefined"
  ) {
    return [];
  }

  try {
    const raw =
      window.localStorage.getItem(
        STORAGE_KEY
      );

    if (!raw) {
      return [];
    }

    const parsed =
      JSON.parse(raw);

    if (
      !Array.isArray(parsed)
    ) {
      return [];
    }

    return parsed;
  } catch (error) {
    console.warn(
      "Could not load transaction tracker:",
      error
    );

    return [];
  }
}

function saveTransactions(
  transactions: TrackedTransaction[]
) {
  if (
    typeof window ===
    "undefined"
  ) {
    return;
  }

  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(
        transactions
      )
    );
  } catch (error) {
    console.warn(
      "Could not save transaction tracker:",
      error
    );
  }
}

/* =========================================================
   STATUS PRESENTATION
   ========================================================= */

const STATUS_ORDER: GenLayerStatusName[] =
  [
    "PENDING",
    "PROPOSING",
    "COMMITTING",
    "REVEALING",
    "ACCEPTED",
    "FINALIZED",
  ];

function statusTitle(
  status: GenLayerStatusName
) {
  switch (status) {
    case "PENDING":
      return "Pending";

    case "PROPOSING":
      return "Proposing";

    case "COMMITTING":
      return "Committing";

    case "REVEALING":
      return "Revealing";

    case "ACCEPTED":
      return "Accepted";

    case "FINALIZED":
      return "Finalized";

    case "UNDETERMINED":
      return "Undetermined";

    case "CANCELED":
      return "Canceled";

    case "APPEAL_REVEALING":
      return "Appeal revealing";

    case "APPEAL_COMMITTING":
      return "Appeal committing";

    case "VALIDATORS_TIMEOUT":
      return "Validators timeout";

    case "LEADER_TIMEOUT":
      return "Leader timeout";

    case "LEADER_REVEALING":
      return "Leader revealing";

    case "UNINITIALIZED":
      return "Initializing";

    default:
      return "Processing";
  }
}

function statusMessage(
  tx: TrackedTransaction
) {
  const status =
    tx.statusName;

  switch (status) {
    case "PENDING":
      return "Your transaction is queued and waiting for activation.";

    case "PROPOSING":
      return "A GenLayer leader is preparing the execution result.";

    case "COMMITTING":
      return "Validators are committing their consensus votes.";

    case "REVEALING":
      return "Validators are revealing their votes.";

    case "ACCEPTED":
      if (
        tx.resolutionAction ===
        "Finalize"
      ) {
        return "The decision has been accepted and the finalization action is now available. Waiting for the finalized state.";
      }

      return "GenLayer validators accepted the decision. The appeal/finality window is still in progress.";

    case "FINALIZED":
      if (
        tx.state ===
        "SUCCESS"
      ) {
        return "Transaction finalized successfully.";
      }

      return "Transaction reached finality.";

    case "UNDETERMINED":
      return "This consensus round was undetermined. GenLayer is still processing the transaction lifecycle.";

    case "CANCELED":
      return "The transaction was canceled before final completion.";

    case "APPEAL_REVEALING":
      return "An appeal round is currently revealing validator votes.";

    case "APPEAL_COMMITTING":
      return "An appeal round is currently collecting validator commitments.";

    case "VALIDATORS_TIMEOUT":
      return "Validator processing timed out. The transaction remains in its GenLayer lifecycle.";

    case "LEADER_TIMEOUT":
      return "The leader execution timed out. The transaction remains in its GenLayer lifecycle.";

    case "LEADER_REVEALING":
      return "The leader is revealing execution data before validator voting.";

    default:
      return "GenLayer is processing the transaction.";
  }
}

/* =========================================================
   STATUS PROGRESS
   ========================================================= */

function statusIndex(
  status: GenLayerStatusName
) {
  const index =
    STATUS_ORDER.indexOf(
      status
    );

  return index === -1
    ? 0
    : index;
}

function statusProgress(
  status: GenLayerStatusName
) {
  if (
    status ===
    "FINALIZED"
  ) {
    return 100;
  }

  const index =
    statusIndex(status);

  return Math.round(
    (index /
      (STATUS_ORDER.length -
        1)) *
      100
  );
}

/* =========================================================
   TRANSACTION STATUS CARD
   ========================================================= */

function TransactionCard({
  tx,
}: {
  tx: TrackedTransaction;
}) {
  const progress =
    statusProgress(
      tx.statusName
    );

  const isTerminal =
    tx.state ===
      "SUCCESS" ||
    tx.state ===
      "FAILED";

  return (
    <article
      className="card"
      style={{
        marginBottom: 16,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent:
            "space-between",
          gap: 16,
          alignItems:
            "flex-start",
        }}
      >
        <div>
          <span className="eyebrow">
            TRANSACTION
          </span>

          <h3
            style={{
              marginTop: 6,
              marginBottom: 4,
            }}
          >
            {tx.title}
          </h3>

          <p
            style={{
              margin: 0,
              opacity: 0.65,
              fontSize: 13,
            }}
          >
            {tx.kind ===
            "CREATE_POLICY"
              ? "Create protection policy"
              : `Evaluate policy #${tx.policyId ?? "—"}`}
          </p>
        </div>

        <span
          className={`badge ${
            tx.state ===
            "SUCCESS"
              ? "d1"
              : tx.state ===
                  "FAILED"
                ? "d0"
                : ""
          }`}
        >
          {statusTitle(
            tx.statusName
          )}
        </span>
      </div>

      <div
        style={{
          marginTop: 18,
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent:
              "space-between",
            fontSize: 12,
            opacity: 0.65,
            marginBottom: 8,
          }}
        >
          <span>
            GenLayer lifecycle
          </span>

          <span>
            {progress}%
          </span>
        </div>

        <div
          style={{
            width: "100%",
            height: 6,
            borderRadius: 99,
            background:
              "rgba(127,127,127,.18)",
            overflow:
              "hidden",
          }}
        >
          <div
            style={{
              width: `${progress}%`,
              height: "100%",
              borderRadius: 99,
              background:
                "currentColor",
              transition:
                "width .4s ease",
            }}
          />
        </div>
      </div>

      <div
        style={{
          marginTop: 18,
        }}
      >
        <p
          style={{
            margin: 0,
            lineHeight: 1.6,
          }}
        >
          {statusMessage(tx)}
        </p>
      </div>

      <div
        className="data"
        style={{
          marginTop: 18,
        }}
      >
        <div>
          <small>
            Status
          </small>

          <b>
            {tx.statusName}
          </b>
        </div>

        <div>
          <small>
            Queue
          </small>

          <b>
            {tx.queuePosition ??
              "—"}
          </b>
        </div>

        <div>
          <small>
            Execution
          </small>

          <b
            style={{
              fontSize: 12,
            }}
          >
            {tx.txExecutionResultName ??
              "Processing"}
          </b>
        </div>
      </div>

      {tx.statusName ===
        "ACCEPTED" && (
        <div
          style={{
            marginTop: 16,
            padding: 12,
            borderRadius: 10,
            background:
              "rgba(127,127,127,.08)",
            fontSize: 13,
            lineHeight: 1.55,
          }}
        >
          <strong>
            Accepted ≠ Finalized
          </strong>

          <br />

          The validator decision has been
          accepted, but GenLayer may still
          be inside the finalization/appeal
          window. This is normal.
        </div>
      )}

      {tx.resolutionAction && (
        <div
          style={{
            marginTop: 12,
            fontSize: 12,
            opacity: 0.65,
          }}
        >
          Protocol action:{" "}
          <strong>
            {tx.resolutionAction}
          </strong>
        </div>
      )}

      <div
        className="actions"
        style={{
          marginTop: 18,
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <a
          className="ghost"
          href="https://explorer-bradbury.genlayer.com"
          target="_blank"
          rel="noreferrer"
        >
          Open Bradbury explorer
        </a>

        <button
          className="ghost"
          type="button"
          onClick={() => {
            navigator.clipboard
              ?.writeText(tx.hash)
              .catch(() => {});

            alert(
              "Transaction hash copied."
            );
          }}
        >
          Copy hash
        </button>
      </div>

      <code
        style={{
          display: "block",
          marginTop: 12,
          wordBreak:
            "break-all",
          fontSize: 11,
          opacity: 0.6,
        }}
      >
        {tx.hash}
      </code>

      {tx.error && (
        <div
          style={{
            marginTop: 14,
            padding: 12,
            borderRadius: 10,
            background:
              "rgba(220,50,50,.08)",
            fontSize: 13,
            lineHeight: 1.5,
          }}
        >
          {tx.error}
        </div>
      )}

      {isTerminal &&
        tx.state ===
          "SUCCESS" && (
          <div
            style={{
              marginTop: 14,
              fontSize: 13,
            }}
          >
            ✓ This transaction is
            finalized and execution
            completed successfully.
          </div>
        )}
    </article>
  );
}

/* =========================================================
   MAIN APP
   ========================================================= */

export default function Home() {
  const [
    wallet,
    setWallet,
  ] =
    useState<
      `0x${string}` | null
    >(null);

  const [
    provider,
    setProvider,
  ] =
    useState<
      EthereumProvider | null
    >(null);

  const [
    policies,
    setPolicies,
  ] =
    useState<
      Policy[]
    >([]);

  const [
    transactions,
    setTransactions,
  ] =
    useState<
      TrackedTransaction[]
    >([]);

  const [
    flight,
    setFlight,
  ] =
    useState("");

  const [
    date,
    setDate,
  ] =
    useState("");

  const [
    url,
    setUrl,
  ] =
    useState("");

  const [
    amount,
    setAmount,
  ] =
    useState("100");

  const [
    busy,
    setBusy,
  ] =
    useState(false);

  const [
    active,
    setActive,
  ] =
    useState<
      string | null
    >(null);

  const [
    msg,
    setMsg,
  ] =
    useState("");

  /*
   * Prevent duplicate polling loops.
   */
  const monitors =
    useRef<
      Set<string>
    >(new Set());

  /* =======================================================
     TRANSACTION STATE UPDATE
     ======================================================= */

  const updateTransaction =
    useCallback(
      (
        hash: string,
        update: Partial<TrackedTransaction>
      ) => {
        setTransactions(
          (current) => {
            const next =
              current.map(
                (tx) =>
                  tx.hash === hash
                    ? {
                        ...tx,
                        ...update,
                        updatedAt:
                          Date.now(),
                      }
                    : tx
              );

            saveTransactions(
              next
            );

            return next;
          }
        );
      },
      []
    );

  /* =======================================================
     REFRESH POLICIES
     ======================================================= */

  const refresh =
    useCallback(
      async (
        address = wallet
      ) => {
        if (!address) {
          return;
        }

        try {
          const result =
            await readPolicies(
              address
            );

          setPolicies(
            result
          );
        } catch (error) {
          console.error(
            "Policy refresh failed:",
            error
          );
        }
      },
      [wallet]
    );

  /* =======================================================
     TRACK ONE TRANSACTION
     ======================================================= */

  const trackTransaction =
    useCallback(
      async (
        tx: TrackedTransaction
      ) => {
        if (
          monitors.current.has(
            tx.hash
          )
        ) {
          return;
        }

        /*
         * Never monitor transactions that
         * are already successfully finalized.
         */
        if (
          tx.state ===
            "SUCCESS" ||
          tx.state ===
            "FAILED"
        ) {
          return;
        }

        monitors.current.add(
          tx.hash
        );

        try {
          while (
            true
          ) {
            let snapshot:
              GenLayerTransactionSnapshot;

            try {
              snapshot =
                await getTransactionSnapshot(
                  tx.hash
                );
            } catch (error) {
              console.warn(
                "Could not read transaction:",
                error
              );

              updateTransaction(
                tx.hash,
                {
                  state:
                    "PAUSED",
                  error:
                    "Temporary connection problem. The transaction is still saved and monitoring will resume automatically.",
                }
              );

              await new Promise<void>(
                (resolve) =>
                  setTimeout(
                    resolve,
                    8000
                  )
              );

              continue;
            }

            const successful =
              snapshot.statusName ===
                "FINALIZED" &&
              isSuccessfulExecution(
                snapshot
              );

            const failed =
              snapshot.statusName ===
                "CANCELED" ||
              (
                snapshot.statusName ===
                  "FINALIZED" &&
                snapshot
                  .txExecutionResultName &&
                !successful
              );

            updateTransaction(
              tx.hash,
              {
                statusName:
                  snapshot.statusName,

                statusCode:
                  snapshot.statusCode,

                txExecutionResultName:
                  snapshot.txExecutionResultName,

                queuePosition:
                  snapshot.queuePosition,

                lifecycle:
                  snapshot.lifecycle,

                projectedStatus:
                  snapshot.projectedStatus,

                resolutionAction:
                  snapshot.resolutionAction,

                resolutionSource:
                  snapshot.resolutionSource,

                state:
                  successful
                    ? "SUCCESS"
                    : failed
                      ? "FAILED"
                      : "TRACKING",

                error:
                  failed
                    ? `Transaction finished with ${snapshot.txExecutionResultName ?? snapshot.statusName}.`
                    : undefined,
              }
            );

            /*
             * Finalized + successful.
             */
            if (
              successful
            ) {
              await refresh();

              setMsg(
                tx.kind ===
                  "CREATE_POLICY"
                  ? "Policy created successfully and finalized on GenLayer."
                  : "Flight evaluation finalized successfully."
              );

              break;
            }

            /*
             * Canceled or finalized with
             * execution error.
             */
            if (
              failed
            ) {
              setMsg(
                `Transaction finished without a successful execution: ${
                  snapshot.txExecutionResultName ??
                  snapshot.statusName
                }.`
              );

              break;
            }

            /*
             * Still processing.
             */
            await new Promise<void>(
              (resolve) =>
                setTimeout(
                  resolve,
                  5000
                )
            );
          }
        } finally {
          monitors.current.delete(
            tx.hash
          );
        }
      },
      [
        refresh,
        updateTransaction,
      ]
    );

  /* =======================================================
     CREATE TRACKED TRANSACTION
     ======================================================= */

  const addTransaction =
    useCallback(
      (
        tx: TrackedTransaction
      ) => {
        setTransactions(
          (current) => {
            /*
             * Prevent duplicate hashes.
             */
            const exists =
              current.some(
                (item) =>
                  item.hash ===
                  tx.hash
              );

            if (
              exists
            ) {
              return current;
            }

            const next = [
              tx,
              ...current,
            ];

            saveTransactions(
              next
            );

            return next;
          }
        );
      },
      []
    );

  /* =======================================================
     CONNECT WALLET
     ======================================================= */

  async function connect() {
    try {
      const result =
        await connectWallet();

      setWallet(
        result.address
      );

      setProvider(
        result.provider
      );

      await refresh(
        result.address
      );
    } catch (error) {
      setMsg(
        error instanceof Error
          ? error.message
          : "Wallet connection failed."
      );
    }
  }

  /* =======================================================
     CREATE POLICY
     ======================================================= */

  async function create(
    event: React.FormEvent
  ) {
    event.preventDefault();

    if (
      !wallet ||
      !provider
    ) {
      setMsg(
        "Connect your wallet first."
      );

      return;
    }

    if (
      !url.startsWith(
        "https://"
      )
    ) {
      setMsg(
        "Use an HTTPS flight-status source URL."
      );

      return;
    }

    try {
      setBusy(
        true
      );

      setMsg(
        "Waiting for MetaMask approval..."
      );

      const hash =
        await createPolicy(
          wallet,
          provider,
          {
            flightNumber:
              flight,

            departureDate:
              date,

            sourceUrl:
              url,

            payoutAmount:
              amount,
          },
          (submittedHash) => {
            setMsg(
              "Transaction submitted. Saving transaction tracker..."
            );

            /*
             * IMPORTANT:
             *
             * Persist the transaction immediately
             * after we receive its hash.
             */
            addTransaction({
              id: submittedHash,

              hash:
                submittedHash,

              kind:
                "CREATE_POLICY",

              title:
                `Protect ${flight.toUpperCase()}`,

              createdAt:
                Date.now(),

              updatedAt:
                Date.now(),

              statusName:
                "PENDING",

              state:
                "TRACKING",
            });
          }
        );

      setMsg(
        `Policy transaction submitted: ${short(
          hash
        )}. GenLayer is processing it.`
      );

      setFlight("");
      setDate("");
      setUrl("");

      /*
       * Start monitoring AFTER the hash has
       * already been persisted.
       */
      const tracked =
        loadTransactions().find(
          (tx) =>
            tx.hash ===
            hash
        );

      if (
        tracked
      ) {
        void trackTransaction(
          tracked
        );
      }
    } catch (error) {
      setMsg(
        error instanceof Error
          ? error.message
          : "Could not create policy."
      );
    } finally {
      setBusy(
        false
      );
    }
  }

  /* =======================================================
     EVALUATE POLICY
     ======================================================= */

  async function evaluate(
    policyId: string
  ) {
    if (
      !wallet ||
      !provider
    ) {
      setMsg(
        "Connect your wallet first."
      );

      return;
    }

    try {
      setBusy(
        true
      );

      setActive(
        policyId
      );

      setMsg(
        "Waiting for MetaMask approval..."
      );

      const hash =
        await evaluatePolicy(
          wallet,
          provider,
          policyId,
          (submittedHash) => {
            setMsg(
              "Evaluation submitted. Saving transaction tracker..."
            );

            addTransaction({
              id: submittedHash,

              hash:
                submittedHash,

              kind:
                "EVALUATE_POLICY",

              title:
                `Evaluate policy #${policyId}`,

              policyId,

              createdAt:
                Date.now(),

              updatedAt:
                Date.now(),

              statusName:
                "PENDING",

              state:
                "TRACKING",
            });
          }
        );

      setMsg(
        `Evaluation submitted: ${short(
          hash
        )}. GenLayer validators are processing it.`
      );

      const tracked =
        loadTransactions().find(
          (tx) =>
            tx.hash ===
            hash
        );

      if (
        tracked
      ) {
        void trackTransaction(
          tracked
        );
      }
    } catch (error) {
      setMsg(
        error instanceof Error
          ? error.message
          : "Evaluation failed."
      );
    } finally {
      setBusy(
        false
      );

      setActive(
        null
      );
    }
  }

  /* =======================================================
     LOAD PERSISTED TRANSACTIONS
     ======================================================= */

  useEffect(() => {
    const stored =
      loadTransactions();

    setTransactions(
      stored
    );

    /*
     * Resume every transaction that was
     * still processing when the user last
     * closed/refreshed the browser.
     */
    for (
      const tx of stored
    ) {
      if (
        tx.state ===
          "TRACKING" ||
        tx.state ===
          "PAUSED"
      ) {
        void trackTransaction(
          tx
        );
      }
    }
  }, [
    trackTransaction,
  ]);

  /* =======================================================
     AUTO CONNECT EXISTING WALLET
     ======================================================= */

  useEffect(() => {
    const ethereum =
      (window as any)
        .ethereum as
        | EthereumProvider
        | undefined;

    if (
      !ethereum
    ) {
      return;
    }

    ethereum
      .request({
        method:
          "eth_accounts",
      })
      .then(
        (accounts) => {
          const list =
            accounts as string[];

          if (
            list?.[0]
          ) {
            setWallet(
              list[0] as `0x${string}`
            );

            setProvider(
              ethereum
            );
          }
        }
      )
      .catch(
        () => {}
      );
  }, []);

  /* =======================================================
     REFRESH POLICIES WHEN WALLET CHANGES
     ======================================================= */

  useEffect(() => {
    if (
      wallet
    ) {
      void refresh(
        wallet
      );
    }
  }, [
    wallet,
    refresh,
  ]);

  /* =======================================================
     WALLET EVENTS
     ======================================================= */

  useEffect(() => {
    const ethereum =
      (window as any)
        .ethereum;

    if (
      !ethereum?.on
    ) {
      return;
    }

    const handleAccountsChanged =
      (accounts: string[]) => {
        const next =
          accounts?.[0];

        if (
          next
        ) {
          setWallet(
            next as `0x${string}`
          );

          setProvider(
            ethereum
          );
        } else {
          setWallet(
            null
          );

          setProvider(
            null
          );

          setPolicies(
            []
          );
        }
      };

    ethereum.on(
      "accountsChanged",
      handleAccountsChanged
    );

    return () => {
      ethereum.removeListener?.(
        "accountsChanged",
        handleAccountsChanged
      );
    };
  }, []);

  /* =======================================================
     RENDER
     ======================================================= */

  return (
    <main className="shell">

      {/* =================================================
          NAV
          ================================================= */}

      <nav className="nav">
        <div className="brand">
          <div className="mark">
            <i />
            <i />
            <i />
          </div>

          <div>
            <b>
              FlightGuard
            </b>

            <small>
              Powered by GenLayer
            </small>
          </div>
        </div>

        <button
          className="ghost"
          onClick={
            connect
          }
        >
          {wallet
            ? short(wallet)
            : "Connect wallet"}
        </button>
      </nav>

      {/* =================================================
          HERO
          ================================================= */}

      <section className="hero">
        <span className="eyebrow">
          REAL-WORLD DECISIONS ONCHAIN
        </span>

        <h1>
          Flight protection,
          <br />
          <em>
            resolved by GenLayer.
          </em>
        </h1>

        <p>
          Create a flight protection policy
          and let a GenLayer Intelligent
          Contract evaluate live external
          evidence when a disruption occurs.
        </p>
      </section>

      {/* =================================================
          CREATE + HOW IT WORKS
          ================================================= */}

      <section className="grid">

        <div className="card">
          <span className="eyebrow">
            01 / CREATE
          </span>

          <h2>
            Protect a flight
          </h2>

          <form
            onSubmit={
              create
            }
          >
            <label>
              Flight number

              <input
                value={
                  flight
                }
                onChange={
                  (event) =>
                    setFlight(
                      event.target
                        .value
                    )
                }
                placeholder="BA75"
                required
              />
            </label>

            <label>
              Departure date

              <input
                type="date"
                value={
                  date
                }
                onChange={
                  (event) =>
                    setDate(
                      event.target
                        .value
                    )
                }
                required
              />
            </label>

            <label>
              Flight-status source URL

              <input
                type="url"
                value={
                  url
                }
                onChange={
                  (event) =>
                    setUrl(
                      event.target
                        .value
                    )
                }
                placeholder="https://..."
                required
              />

              <small>
                Use an airline, airport,
                or reputable live
                flight-status page.
              </small>
            </label>

            <label>
              Protection amount

              <input
                value={
                  amount
                }
                onChange={
                  (event) =>
                    setAmount(
                      event.target
                        .value
                    )
                }
                required
              />
            </label>

            <button
              className="primary"
              disabled={
                busy ||
                !wallet
              }
            >
              {busy
                ? "Processing..."
                : "Create protection"}
            </button>
          </form>
        </div>

        <div className="card">
          <span className="eyebrow">
            02 / RESOLVE
          </span>

          <h2>
            How GenLayer decides
          </h2>

          <div className="steps">
            <div>
              <b>
                01
              </b>

              <strong>
                Retrieve
              </strong>

              <p>
                The contract reads the
                supplied live source.
              </p>
            </div>

            <div>
              <b>
                02
              </b>

              <strong>
                Interpret
              </strong>

              <p>
                An LLM extracts the
                relevant flight outcome.
              </p>
            </div>

            <div>
              <b>
                03
              </b>

              <strong>
                Consensus
              </strong>

              <p>
                Validators independently
                reproduce the decision.
              </p>
            </div>

            <div>
              <b>
                04
              </b>

              <strong>
                Record
              </strong>

              <p>
                The agreed result is
                stored in the contract.
              </p>
            </div>
          </div>
        </div>

      </section>

      {/* =================================================
          GENERAL STATUS MESSAGE
          ================================================= */}

      {msg && (
        <section className="status">
          <span className="dot" />

          <div>
            <b>
              Transaction status
            </b>

            <p>
              {msg}
            </p>
          </div>
        </section>
      )}

      {/* =================================================
          PERSISTENT TRANSACTION TRACKER
          ================================================= */}

      {transactions.length >
        0 && (
        <section
          className="policies"
          style={{
            marginTop: 24,
          }}
        >
          <div className="sectionTitle">
            <div>
              <span className="eyebrow">
                02.5 / TRANSACTIONS
              </span>

              <h2>
                Transaction tracker
              </h2>
            </div>

            <button
              className="ghost"
              onClick={() => {
                const current =
                  loadTransactions();

                setTransactions(
                  current
                );

                for (
                  const tx of
                    current
                ) {
                  if (
                    tx.state ===
                      "TRACKING" ||
                    tx.state ===
                      "PAUSED"
                  ) {
                    void trackTransaction(
                      tx
                    );
                  }
                }
              }}
            >
              Resume tracking
            </button>
          </div>

          <p
            style={{
              opacity: 0.65,
              lineHeight: 1.6,
              marginBottom: 20,
            }}
          >
            Transactions are saved in this
            browser. If you refresh or close
            the page while GenLayer is still
            processing, the same transaction
            hash is recovered and monitored
            again instead of submitting a
            duplicate transaction.
          </p>

          {transactions.map(
            (tx) => (
              <TransactionCard
                key={
                  tx.id
                }
                tx={
                  tx
                }
              />
            )
          )}
        </section>
      )}

      {/* =================================================
          POLICIES
          ================================================= */}

      <section className="policies">
        <div className="sectionTitle">
          <div>
            <span className="eyebrow">
              03 / YOUR POLICIES
            </span>

            <h2>
              Flight protection dashboard
            </h2>
          </div>

          <button
            className="ghost"
            onClick={() =>
              refresh()
            }
          >
            Refresh
          </button>
        </div>

        {!wallet ? (
          <div className="empty">
            Connect your wallet to view
            policies.
          </div>
        ) : policies.length ===
          0 ? (
          <div className="empty">
            No policies yet. Create your
            first flight protection above.
          </div>
        ) : (
          <div className="list">
            {policies.map(
              (policy) => (
                <article
                  className="policy"
                  key={
                    policy.policy_id
                  }
                >
                  <div className="top">
                    <div>
                      <small>
                        POLICY #
                        {
                          policy.policy_id
                        }
                      </small>

                      <h3>
                        {
                          policy.flight_number
                        }
                      </h3>

                      <p>
                        {
                          policy.departure_date
                        }
                      </p>
                    </div>

                    <span
                      className={`badge d${policy.decision}`}
                    >
                      {label(
                        policy.decision
                      )}
                    </span>
                  </div>

                  <div className="data">
                    <div>
                      <small>
                        Protection
                      </small>

                      <b>
                        {
                          policy.payout_amount
                        }
                      </b>
                    </div>

                    <div>
                      <small>
                        Contract state
                      </small>

                      <b>
                        {
                          policy.status
                        }
                      </b>
                    </div>
                  </div>

                  {policy.summary && (
                    <div className="evidence">
                      <small>
                        Resolution summary
                      </small>

                      <p>
                        {
                          policy.summary
                        }
                      </p>

                      {policy.evidence && (
                        <>
                          <small>
                            Evidence excerpt
                          </small>

                          <p>
                            {
                              policy.evidence
                            }
                          </p>
                        </>
                      )}
                    </div>
                  )}

                  <div className="actions">
                    {policy.decision ===
                      -1 && (
                      <button
                        className="primary small"
                        disabled={
                          busy
                        }
                        onClick={() =>
                          evaluate(
                            policy.policy_id
                          )
                        }
                      >
                        {active ===
                        policy.policy_id
                          ? "Submitting..."
                          : "Evaluate with GenLayer"}
                      </button>
                    )}

                    <a
                      className="ghost"
                      href={
                        policy.source_url
                      }
                      target="_blank"
                      rel="noreferrer"
                    >
                      View source
                    </a>
                  </div>
                </article>
              )
            )}
          </div>
        )}
      </section>

      {/* =================================================
          FOOTER
          ================================================= */}

      <footer>
        <span>
          FlightGuard · GenLayer Intelligent
          Contract demo
        </span>

        <span>
          Protection metadata only · no real
          funds are transferred
        </span>
      </footer>
    </main>
  );
}