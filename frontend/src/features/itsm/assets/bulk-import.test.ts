import { describe, expect, it } from "vitest";

import {
  buildImport,
  detectDelimiter,
  parseDelimited,
  templateCsv,
} from "./bulk-import";

describe("parseDelimited", () => {
  it("keeps a delimiter that sits inside a quoted field", () => {
    const rows = parseDelimited('a,b\n"Bangalore, India",2');
    expect(rows[1]).toEqual(["Bangalore, India", "2"]);
  });

  it("unescapes doubled quotes", () => {
    const rows = parseDelimited('a\n"He said ""hi"""');
    expect(rows[1][0]).toBe('He said "hi"');
  });

  it("handles CRLF and a missing trailing newline", () => {
    const rows = parseDelimited("a,b\r\n1,2\r\n3,4");
    expect(rows).toEqual([
      ["a", "b"],
      ["1", "2"],
      ["3", "4"],
    ]);
  });

  it("drops blank lines", () => {
    expect(parseDelimited("a,b\n\n1,2\n")).toHaveLength(2);
  });
});

describe("detectDelimiter", () => {
  it("detects tabs from an Excel copy-paste", () => {
    expect(detectDelimiter("a\tb\tc\n1\t2\t3")).toBe("\t");
  });

  it("falls back to comma", () => {
    expect(detectDelimiter("a,b,c")).toBe(",");
  });
});

describe("buildImport", () => {
  const header = "Asset Tag,Asset Name,Asset Type,Cost,Currency,Asset State";

  it("rejects a file missing a required column", () => {
    const res = buildImport(parseDelimited("Asset Name,Cost\nThing,10"));
    expect(res.valid).toHaveLength(0);
    expect(res.errors[0].message).toMatch(/Asset Tag/);
  });

  it("imports a good row and normalises currency", () => {
    const res = buildImport(
      parseDelimited(
        `${header}\nNEW_TAG_1,Test laptop,Laptop,1200,usd,In Stock`,
      ),
    );
    expect(res.errors).toHaveLength(0);
    expect(res.valid).toHaveLength(1);
    expect(res.valid[0].currency).toBe("USD");
    expect(res.valid[0].cost).toBe(1200);
  });

  it("warns and falls back on an unknown asset state", () => {
    const res = buildImport(
      parseDelimited(`${header}\nNEW_TAG_2,Test,Laptop,10,INR,Teleported`),
    );
    expect(res.valid[0].assetState).toBe("In Stock");
    expect(res.warnings.some((w) => /Asset State/.test(w.message))).toBe(true);
  });

  it("rejects a tag duplicated within the same file but keeps the first", () => {
    const res = buildImport(
      parseDelimited(
        `${header}\nDUP_TAG,One,Laptop,1,INR,In Stock\nDUP_TAG,Two,Laptop,1,INR,In Stock`,
      ),
    );
    expect(res.valid).toHaveLength(1);
    expect(res.errors[0].message).toMatch(/more than once/);
  });

  it("rejects a tag that already exists in the inventory", () => {
    const res = buildImport(
      parseDelimited(`${header}\nBLR_FAP10,Clash,Access Point,1,INR,In Stock`),
      ["BLR_FAP10"],
    );
    expect(res.valid).toHaveLength(0);
    expect(res.errors[0].message).toMatch(/already exists/);
  });

  it("keeps good rows when a sibling row is bad", () => {
    const res = buildImport(
      parseDelimited(
        `${header}\nGOOD_TAG_1,Fine,Laptop,1,INR,In Stock\n,Missing tag,Laptop,1,INR,In Stock`,
      ),
    );
    expect(res.valid).toHaveLength(1);
    expect(res.errors).toHaveLength(1);
  });

  it("ships a template that parses back cleanly", () => {
    const res = buildImport(parseDelimited(templateCsv()));
    expect(res.errors).toHaveLength(0);
    expect(res.valid).toHaveLength(1);
  });
});
