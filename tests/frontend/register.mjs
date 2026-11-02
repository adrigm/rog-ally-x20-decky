import { registerHooks } from "node:module";

// Node strips the source types for tests; resolve the ESM .js source reference
// to its .ts file, as TypeScript and Rollup already do for the production build.
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (context.parentURL?.includes("/src/") && specifier.startsWith("./") && specifier.endsWith(".js")) {
      return nextResolve(specifier.slice(0, -3) + ".ts", context);
    }
    return nextResolve(specifier, context);
  },
});
