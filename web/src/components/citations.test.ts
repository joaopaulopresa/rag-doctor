import { splitCitations } from "./citations";

describe("splitCitations", () => {
  it("separates text from single and grouped markers", () => {
    expect(splitCitations("Yes [1]. Also [2, 4].")).toEqual([
      { kind: "text", text: "Yes " },
      { kind: "cite", numbers: [1] },
      { kind: "text", text: ". Also " },
      { kind: "cite", numbers: [2, 4] },
      { kind: "text", text: "." },
    ]);
  });

  it("leaves text without markers whole", () => {
    expect(splitCitations("The passages do not answer.")).toEqual([{ kind: "text", text: "The passages do not answer." }]);
  });

  it("does not treat words in brackets as citations", () => {
    expect(splitCitations("[sic] and [a]")).toEqual([{ kind: "text", text: "[sic] and [a]" }]);
  });
});
