import styles from "./SimpleMarkdown.module.css";

/**
 * The small subset of Markdown the policies and instructions pages use:
 * #/##/### headings, "- " lists, **bold**, and paragraphs. Deliberately
 * not a Markdown library — these are admin-authored policy texts and one
 * generated instructions page, and a dependency is not justified for
 * headings and lists. Everything renders as text nodes; nothing is ever
 * injected as HTML.
 */

function inline(text, keyBase) {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return parts.map((part, i) =>
    i % 2 === 1 ? <strong key={`${keyBase}-${i}`}>{part}</strong> : part
  );
}

function SimpleMarkdown({ markdown }) {
  const blocks = [];
  const lines = markdown.split("\n");
  let paragraph = [];
  let list = null;

  const flushParagraph = () => {
    if (paragraph.length > 0) {
      blocks.push({ type: "p", text: paragraph.join(" ") });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list !== null) {
      blocks.push({ type: "ul", items: list });
      list = null;
    }
  };

  for (const line of lines) {
    const heading = line.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ type: `h${heading[1].length}`, text: heading[2] });
    } else if (line.match(/^-\s+/)) {
      flushParagraph();
      if (list === null) list = [];
      list.push(line.replace(/^-\s+/, ""));
    } else if (line.trim() === "") {
      flushParagraph();
      flushList();
    } else if (list !== null) {
      // A wrapped continuation of the previous list item.
      list[list.length - 1] += ` ${line.trim()}`;
    } else {
      paragraph.push(line.trim());
    }
  }
  flushParagraph();
  flushList();

  return (
    <div className={styles.markdown}>
      {blocks.map((block, i) => {
        if (block.type === "h1")
          return <h1 key={i}>{inline(block.text, i)}</h1>;
        if (block.type === "h2")
          return <h2 key={i}>{inline(block.text, i)}</h2>;
        if (block.type === "h3")
          return <h3 key={i}>{inline(block.text, i)}</h3>;
        if (block.type === "ul")
          return (
            <ul key={i}>
              {block.items.map((item, j) => (
                <li key={j}>{inline(item, `${i}-${j}`)}</li>
              ))}
            </ul>
          );
        return <p key={i}>{inline(block.text, i)}</p>;
      })}
    </div>
  );
}

export default SimpleMarkdown;
