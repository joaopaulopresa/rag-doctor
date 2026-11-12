import { useEffect, useRef, useState } from "react";
import type { Job } from "../types";

interface Props {
  job: Job;
  onFinish?: (job: Job) => void;
  compact?: boolean;
}

/** Live progress of a background job, from the API's server-sent events. */
export function JobProgress({ job: initial, onFinish, compact }: Props) {
  const [job, setJob] = useState<Job>(initial);
  const finished = useRef(false);

  useEffect(() => {
    finished.current = initial.status === "done" || initial.status === "failed";
    setJob(initial);
    if (finished.current) return;
    const source = new EventSource(`/api/admin/jobs/${initial.id}/events`);
    source.onmessage = (message) => {
      const next = JSON.parse(message.data) as Job | null;
      if (!next) return;
      setJob(next);
      if ((next.status === "done" || next.status === "failed") && !finished.current) {
        finished.current = true;
        source.close();
        onFinish?.(next);
      }
    };
    return () => source.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial.id]);

  if (job.status === "done" && compact) return null;
  const share = job.total ? job.done / job.total : 0;
  return (
    <div className={`job ${job.status}`} role="status">
      <div className="spread">
        <span className="row">
          {(job.status === "running" || job.status === "queued") && <span className="spinner" />}
          <span>
            {job.status === "queued" ? "Waiting for the worker" : job.status === "failed" ? "Failed" : job.message || job.title}
          </span>
        </span>
        {job.total > 0 && (
          <span className="faint">
            {job.done} of {job.total}
          </span>
        )}
      </div>
      {job.status === "running" && job.total > 0 && (
        <div className="bar">
          <span style={{ width: `${Math.round(share * 100)}%` }} />
        </div>
      )}
      {job.status === "failed" && <p className="notice error">{job.error}</p>}
    </div>
  );
}
