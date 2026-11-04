import {
  type AsyncBuffer,
  asyncBufferFromUrl,
  cachedAsyncBuffer,
  type ColumnData,
  type Compressors,
  type FileMetaData,
  parquetMetadataAsync,
  parquetRead,
} from "hyparquet";
import { compressors } from "hyparquet-compressors";

import { ColumnStore, concatenate, type ColumnLoader, type ColumnSource } from "./columns";

export type OpenParquet = (source: ColumnSource) => Promise<AsyncBuffer>;

interface OpenFile {
  file: AsyncBuffer;
  metadata: FileMetaData;
}

/**
 * Reads single columns out of Parquet files with hyparquet. `open` supplies the bytes: HTTP range
 * requests in the browser, a local file in Node tests. Each file's footer is read once.
 */
export function createParquetLoader(open: OpenParquet, codecs?: Compressors): ColumnLoader {
  const files = new Map<string, Promise<OpenFile>>();

  const openFile = (source: ColumnSource): Promise<OpenFile> => {
    let pending = files.get(source.url);
    if (!pending) {
      pending = (async () => {
        const file = await open(source);
        return { file, metadata: await parquetMetadataAsync(file) };
      })();
      files.set(source.url, pending);
      pending.catch(() => {
        if (files.get(source.url) === pending) {
          files.delete(source.url);
        }
      });
    }
    return pending;
  };

  return async (source, column) => {
    const { file, metadata } = await openFile(source);
    const chunks: ColumnData[] = [];
    await parquetRead({ file, metadata, columns: [column], compressors: codecs, onChunk: (c) => chunks.push(c) });
    if (chunks.length === 0) {
      throw new Error(`Column '${column}' is not in the ${source.year} play-by-play file.`);
    }
    // One chunk per row group, in file order.
    chunks.sort((a, b) => a.rowStart - b.rowStart);
    return concatenate(chunks.map((c) => c.columnData));
  };
}

async function openOverHttp(source: ColumnSource): Promise<AsyncBuffer> {
  try {
    return cachedAsyncBuffer(await asyncBufferFromUrl({ url: source.url }));
  } catch (e) {
    throw new Error(
      `Could not read the ${source.year} play-by-play data at ${source.url}: ${e instanceof Error ? e.message : String(e)}`,
    );
  }
}

/** The app's store: columns come over HTTP, one range request per column chunk. */
export const browserColumnStore = new ColumnStore(createParquetLoader(openOverHttp, compressors));
