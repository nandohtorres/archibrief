// Builds a minimal POSIX ustar archive in the browser, so Terraform pasted
// into the form goes through exactly the same upload and ingest path as an
// uploaded .tar (ADR-0045): no new API, no new backend parser. Only plain
// files with short names are needed here.

const BLOCK = 512;
const encoder = new TextEncoder();

export interface TarEntry {
  name: string;
  content: string;
}

function writeString(header: Uint8Array, offset: number, length: number, value: string) {
  const bytes = encoder.encode(value);
  if (bytes.length > length) throw new Error(`tar field too long: ${value}`);
  header.set(bytes, offset);
}

function writeOctal(header: Uint8Array, offset: number, length: number, value: number) {
  // length - 1 octal digits, then a NUL terminator.
  writeString(header, offset, length, value.toString(8).padStart(length - 1, "0") + "\0");
}

function headerFor(name: string, size: number, mtime: number): Uint8Array {
  const header = new Uint8Array(BLOCK);
  writeString(header, 0, 100, name);
  writeOctal(header, 100, 8, 0o644); // mode
  writeOctal(header, 108, 8, 0); // uid
  writeOctal(header, 116, 8, 0); // gid
  writeOctal(header, 124, 12, size);
  writeOctal(header, 136, 12, mtime);
  header.fill(0x20, 148, 156); // checksum field counts as spaces while summing
  header[156] = 0x30; // typeflag "0": regular file
  writeString(header, 257, 6, "ustar\0");
  writeString(header, 263, 2, "00");
  const checksum = header.reduce((sum, byte) => sum + byte, 0);
  writeString(header, 148, 8, checksum.toString(8).padStart(6, "0") + "\0 ");
  return header;
}

export function createTar(
  entries: TarEntry[],
  mtime = Math.floor(Date.now() / 1000),
): Uint8Array<ArrayBuffer> {
  const parts: Uint8Array[] = [];
  for (const entry of entries) {
    if (!/^[A-Za-z0-9._-][A-Za-z0-9._/-]{0,98}$/.test(entry.name) || entry.name.includes("..")) {
      throw new Error(`unsupported file name for the archive: ${entry.name}`);
    }
    const data = encoder.encode(entry.content);
    parts.push(headerFor(entry.name, data.length, mtime), data);
    const padding = (BLOCK - (data.length % BLOCK)) % BLOCK;
    if (padding) parts.push(new Uint8Array(padding));
  }
  parts.push(new Uint8Array(BLOCK * 2)); // end-of-archive marker

  const out = new Uint8Array(parts.reduce((total, part) => total + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}
