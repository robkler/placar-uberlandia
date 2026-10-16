import { responder } from "../lib/chat.js";

export async function POST(req: Request): Promise<Response> {
  return responder(req);
}
