const assert = require("node:assert/strict");
const { createRequire } = require("node:module");
const tailwind = createRequire(require.resolve("tailwindcss/package.json"));
const chokidar = createRequire(tailwind.resolve("chokidar/package.json"));
const braces = chokidar("braces");
assert.deepEqual(braces.expand("item-{red,blue}"), ["item-red","item-blue"]);
for (const depth of [129, 1000, 4998]) {
  const pattern = "{".repeat(depth) + "a,b" + "}".repeat(depth);
  const ast = braces.parse(pattern);
  assert.ok(ast.nodes.length < 10, "Excessive nesting must become a flat literal");
  assert.equal(typeof braces.compile(ast), "string");
  assert.equal(braces.expand(pattern).length, 1);
  assert.equal(braces.stringify(ast).includes("a,b"), true);
}
console.log("Patched braces: normal expansion and deep-pattern regression checks passed.");
