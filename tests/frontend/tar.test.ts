import { createTar } from "../../frontend/lib/tar";

const decoder = new TextDecoder();
const field = (bytes: Uint8Array, start: number, length: number) =>
  decoder.decode(bytes.slice(start, start + length)).split("\0")[0];

describe("createTar (pasted Terraform becomes an archive)", () => {
  const content = 'resource "aws_s3_bucket" "logs" {\n  bucket = "logs"\n}\n';
  const tar = createTar([{ name: "main.tf", content }], 1_700_000_000);

  it("writes one ustar header, the padded file, and the end marker", () => {
    expect(tar.length).toBe(512 + 512 + 1024);
    expect(field(tar, 0, 100)).toBe("main.tf");
    expect(field(tar, 257, 6)).toBe("ustar");
    expect(parseInt(field(tar, 124, 12), 8)).toBe(
      new TextEncoder().encode(content).length,
    );
    expect(decoder.decode(tar.slice(512, 512 + content.length))).toBe(content);
    expect(tar.slice(1024).every((b) => b === 0)).toBe(true);
  });

  it("has a valid header checksum", () => {
    const header = tar.slice(0, 512);
    const stored = parseInt(field(header, 148, 8).trim(), 8);
    header.fill(0x20, 148, 156);
    expect(header.reduce((sum, b) => sum + b, 0)).toBe(stored);
  });

  it("refuses names that could escape or overflow the archive", () => {
    for (const name of [
      "../main.tf",
      "/etc/passwd",
      "a".repeat(120),
      "bad name.tf",
    ]) {
      expect(() => createTar([{ name, content: "x" }])).toThrow();
    }
  });
});
