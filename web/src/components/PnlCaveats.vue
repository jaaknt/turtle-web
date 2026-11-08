<!-- The caveats from docs/specs/web.md, "The P&L model". Keep the two in step. -->
<template>
  <footer class="page-footer">
    <ul>
      <li>
        <strong>Not an equity curve.</strong> Deposits, withdrawals, dividends and FX are never
        imported, so cash is unknowable. The chart is holdings value vs cost basis, not equity.
      </li>
      <li><strong>USD only.</strong> The importer keeps USD rows only.</li>
      <li>
        <strong>Dividends sit inside market value.</strong> Adjusted closes fold dividends into the
        price, while Lightyear pays them out as cash that the importer never sees. Total P&amp;L
        therefore tracks the broker's position value plus dividends received, so a per-position value
        reads slightly above Lightyear's.
      </li>
      <li>
        <strong>Shares follow the broker.</strong> A split while a position is held rescales its share
        count (detected from the bars, as there is no split table), so the Shares column matches
        Lightyear's. Market value never depends on it.
      </li>
      <li>
        <strong>Sell semantics are unverified.</strong> Proceeds are price × quantity − fee − tax;
        no sell has been checked against a statement yet.
      </li>
      <li>
        <strong>Prices are forward-filled.</strong> A symbol with no bar on a given day (halt,
        delisting) keeps its last close. Each position shows its last close date, so staleness is
        visible rather than silent.
      </li>
    </ul>
  </footer>
</template>
