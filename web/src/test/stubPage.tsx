import { useLocation } from "react-router-dom";

/** A stand-in page that prints its name and the URL it was mounted at. */
export const stubPage = (name: string) => () => {
  const { pathname, search } = useLocation();
  return <p data-testid="page">{`${name} ${pathname}${search}`}</p>;
};

/** A stand-in for an inner view: one h2. */
export const stubSection = (name: string) => () => <h2>{name}</h2>;
