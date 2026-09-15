import path from "node:path";

const structuredLayers = new Set(["app", "pages", "features", "shared"]);
const allowedTargets = {
  app: new Set(["app", "pages", "features", "shared"]),
  pages: new Set(["pages", "features", "shared"]),
  features: new Set(["features", "shared"]),
  shared: new Set(["shared"]),
};

function sourceRoot(fileName) {
  const marker = `${path.sep}src${path.sep}`;
  const markerIndex = path.resolve(fileName).lastIndexOf(marker);
  if (markerIndex === -1) {
    return null;
  }
  return path.resolve(fileName).slice(0, markerIndex) + `${path.sep}src`;
}

function moduleLocation(fileName, root) {
  const relativePath = path.relative(root, path.resolve(fileName));
  if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
    return null;
  }
  const [layer, feature] = relativePath.split(path.sep);
  if (!structuredLayers.has(layer)) {
    return null;
  }
  return { layer, feature: layer === "features" ? feature : null };
}

function importedFile(importPath, importer, root) {
  if (importPath.startsWith("@/")) {
    return path.resolve(root, importPath.slice(2));
  }
  if (importPath.startsWith(".")) {
    return path.resolve(path.dirname(importer), importPath);
  }
  return null;
}

function isAllowed(current, target) {
  if (!allowedTargets[current.layer].has(target.layer)) {
    return false;
  }
  if (current.layer === "features" && target.layer === "features") {
    return Boolean(current.feature) && current.feature === target.feature;
  }
  return true;
}

const layerBoundaries = {
  meta: {
    type: "problem",
    docs: {
      description: "Enforce app to pages to features to shared import direction",
    },
    schema: [],
    messages: {
      forbidden:
        "Import from {{target}} violates the {{current}} layer boundary. " +
        "Allowed direction is app -> pages -> features -> shared.",
    },
  },
  create(context) {
    const importer = context.filename;
    const root = sourceRoot(importer);
    const current = root === null ? null : moduleLocation(importer, root);

    function checkNode(node) {
      if (root === null || current === null || typeof node.source?.value !== "string") {
        return;
      }
      const targetFile = importedFile(node.source.value, importer, root);
      const target = targetFile === null ? null : moduleLocation(targetFile, root);
      if (target !== null && !isAllowed(current, target)) {
        context.report({
          node: node.source,
          messageId: "forbidden",
          data: { current: current.layer, target: target.layer },
        });
      }
    }

    return {
      ExportAllDeclaration: checkNode,
      ExportNamedDeclaration: checkNode,
      ImportDeclaration: checkNode,
      ImportExpression: checkNode,
    };
  },
};

export default layerBoundaries;
