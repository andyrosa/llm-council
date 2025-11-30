/**
 * Convert LaTeX delimiters to remark-math compatible format.
 * LLMs often output \(...\) and \[...\] but remark-math expects $...$ and $$...$$.
 */
export function convertLatexDelimiters(text) {
  if (!text) return text;
  // Convert \[ \] to $$ $$ (display math)
  let result = text.replace(/\\\[/g, '$$').replace(/\\\]/g, '$$');
  // Convert \( \) to $ $ (inline math)
  result = result.replace(/\\\(/g, '$').replace(/\\\)/g, '$');
  return result;
}
