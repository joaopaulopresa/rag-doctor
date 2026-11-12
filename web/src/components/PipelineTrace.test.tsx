import { render, screen } from "@testing-library/react";
import { PipelineTrace } from "./PipelineTrace";

const scores = { correctness: 0, faithfulness: 2, citation: 2 };

describe("PipelineTrace", () => {
  it("blames the search when the gold passage is not among the candidates", () => {
    render(<PipelineTrace outcome="not_retrieved" candidates={20} candidateRank={null} hasContext contextSize={5} contextRank={null} scores={scores} />);
    expect(screen.getByText("Gold not found")).toBeInTheDocument();
    const blamed = screen.getByText("The answer went wrong here").closest("li");
    expect(blamed).toHaveTextContent("Search");
  });

  it("blames the context when the gold passage was found and ranked out", () => {
    render(<PipelineTrace outcome="ranked_low" candidates={20} candidateRank={8} hasContext contextSize={5} contextRank={null} scores={scores} />);
    expect(screen.getByText("Gold at rank 8")).toBeInTheDocument();
    expect(screen.getByText("The answer went wrong here").closest("li")).toHaveTextContent("Context");
  });

  it("says what an external system does not expose", () => {
    render(<PipelineTrace outcome="wrong_answer" candidates={null} candidateRank={null} hasContext={false} contextSize={0} contextRank={null} scores={scores} />);
    expect(screen.getByText("Not exposed")).toBeInTheDocument();
    expect(screen.getByText("No passages")).toBeInTheDocument();
    expect(screen.getByText("The answer went wrong here").closest("li")).toHaveTextContent("Answer");
  });

  it("blames nothing for a correct answer", () => {
    render(<PipelineTrace outcome="correct" candidates={20} candidateRank={1} hasContext contextSize={5} contextRank={1} scores={{ ...scores, correctness: 2 }} />);
    expect(screen.queryByText("The answer went wrong here")).not.toBeInTheDocument();
  });
});
